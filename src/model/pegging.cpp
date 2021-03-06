/***************************************************************************
 *                                                                         *
 * Copyright (C) 2007-2013 by Johan De Taeye, frePPLe bvba                 *
 *                                                                         *
 * This library is free software; you can redistribute it and/or modify it *
 * under the terms of the GNU Affero General Public License as published   *
 * by the Free Software Foundation; either version 3 of the License, or    *
 * (at your option) any later version.                                     *
 *                                                                         *
 * This library is distributed in the hope that it will be useful,         *
 * but WITHOUT ANY WARRANTY; without even the implied warranty of          *
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the            *
 * GNU Affero General Public License for more details.                     *
 *                                                                         *
 * You should have received a copy of the GNU Affero General Public        *
 * License along with this program.                                        *
 * If not, see <http://www.gnu.org/licenses/>.                             *
 *                                                                         *
 ***************************************************************************/

#define FREPPLE_CORE
#include "frepple/model.h"

namespace frepple
{

DECLARE_EXPORT const MetaCategory* PeggingIterator::metadata;


int PeggingIterator::initialize()
{
  // Initialize the pegging metadata
  PeggingIterator::metadata = new MetaCategory("pegging","peggings");

  // Initialize the Python type
  PythonType& x = PythonExtension<PeggingIterator>::getType();
  x.setName("peggingIterator");
  x.setDoc("frePPLe iterator for demand pegging");
  x.supportgetattro();
  x.supportiter();
  const_cast<MetaCategory*>(PeggingIterator::metadata)->pythonClass = x.type_object();
  return x.typeReady();
}


DECLARE_EXPORT PeggingIterator::PeggingIterator(const Demand* d)
  : downstream(false), firstIteration(true), first(false)
{
  initType(metadata);
  const Demand::OperationPlan_list &deli = d->getDelivery();
  for (Demand::OperationPlan_list::const_iterator opplaniter = deli.begin();
      opplaniter != deli.end(); ++opplaniter)
  {
    OperationPlan *t = (*opplaniter)->getTopOwner();
    updateStack(t, t->getQuantity(), 0.0, 0);
  }
}


DECLARE_EXPORT PeggingIterator::PeggingIterator(const OperationPlan* opplan, bool b)
  : downstream(b), firstIteration(true), first(false)
{
  initType(metadata);
  if (!opplan) return;
  if (opplan->getTopOwner()->getOperation()->getType() == *OperationSplit::metadata)
    updateStack(
      opplan,
      opplan->getQuantity(),
      0.0,
      0
      );
  else
    updateStack(
      opplan->getTopOwner(),
      opplan->getTopOwner()->getQuantity(),
      0.0,
      0
      );
}


DECLARE_EXPORT PeggingIterator::PeggingIterator(const FlowPlan* fp, bool b)
  : downstream(b), firstIteration(true), first(false)
{
  initType(metadata);
  if (!fp) return;
  updateStack(
    fp->getOperationPlan()->getTopOwner(),
    fp->getOperationPlan()->getQuantity(),
    0.0,
    0
    );
}


DECLARE_EXPORT PeggingIterator::PeggingIterator(const LoadPlan* lp, bool b)
  : downstream(b), firstIteration(true), first(false)
{
  initType(metadata);
  if (!lp) return;
  updateStack(
    lp->getOperationPlan()->getTopOwner(),
    lp->getOperationPlan()->getQuantity(),
    0.0,
    0
    );
}


DECLARE_EXPORT PeggingIterator& PeggingIterator::operator--()
{
  // Validate
  if (states.empty())
    throw LogicException("Incrementing the iterator beyond it's end");
  if (downstream)
    throw LogicException("Decrementing a downstream iterator");

  // Mark the top entry in the stack as invalid, so it can be reused.
  first = true;

  // Find other operationplans to add to the stack
  state t = states.back(); // Copy the top element
  followPegging(t.opplan, t.quantity, t.offset, t.level);

  // Pop invalid top entry from the stack.
  // This will happen if we didn't find an operationplan to replace the
  // top entry.
  if (first) states.pop_back();

  return *this;
}


DECLARE_EXPORT PeggingIterator& PeggingIterator::operator++()
{
  // Validate
  if (states.empty())
    throw LogicException("Incrementing the iterator beyond it's end");
  if (!downstream)
    throw LogicException("Incrementing an upstream iterator");

  // Mark the top entry in the stack as invalid, so it can be reused.
  first = true;

  // Find other operationplans to add to the stack
  state t = states.back(); // Copy the top element
  followPegging(t.opplan, t.quantity, t.offset, t.level);

  // Pop invalid top entry from the stack.
  // This will happen if we didn't find an operationplan to replace the
  // top entry.
  if (first) states.pop_back();

  return *this;
}


DECLARE_EXPORT void PeggingIterator::followPegging
(const OperationPlan* op, double qty, double offset, short lvl)
{
  // Zero quantity operationplans don't have further pegging
  if (!op->getQuantity()) return;

  // For each flowplan ask the buffer to find the pegged operationplans.
  if (downstream)
    for (OperationPlan::FlowPlanIterator i = op->beginFlowPlans();
        i != op->endFlowPlans(); ++i)
    {
      if (i->getQuantity() > ROUNDING_ERROR) // Producing flowplan
        i->getFlow()->getBuffer()->followPegging(*this, &*i, qty, offset, lvl+1);
    }
  else
    for (OperationPlan::FlowPlanIterator i = op->beginFlowPlans();
        i != op->endFlowPlans(); ++i)
    {
      if (i->getQuantity() < -ROUNDING_ERROR) // Consuming flowplan
        i->getFlow()->getBuffer()->followPegging(*this, &*i, qty, offset, lvl+1);
    }

  // Push child operationplans on the stack.
  // The pegged quantity is equal to the ratio of the quantities of the
  // parent and child operationplan.
  for (OperationPlan::iterator j(op); j != OperationPlan::end(); ++j)
    updateStack(
      &*j,
      qty * j->getQuantity() / op->getQuantity(),
      offset * j->getQuantity() / op->getQuantity(),
      lvl+1
      );
}


DECLARE_EXPORT PyObject* PeggingIterator::iternext()
{
  if (firstIteration)
    firstIteration = false;
  else if (downstream)
    operator++();
  else
    operator--();
  if (!operator bool()) return NULL;
  Py_INCREF(this);
  return static_cast<PyObject*>(this);
}


DECLARE_EXPORT PyObject* PeggingIterator::getattro(const Attribute& attr)
{
  if (attr.isA(Tags::tag_operationplan))
    return PythonObject(getOperationPlan());
  if (attr.isA(Tags::tag_quantity))
    return PythonObject(getQuantity());
  if (attr.isA(Tags::tag_level))
    return PythonObject(getLevel());
  return NULL;
}


DECLARE_EXPORT void PeggingIterator::updateStack
(const OperationPlan* op, double qty, double o, short lvl)
{
  // Avoid very small pegging quantities
  if (qty < ROUNDING_ERROR) return;

  if (first)
  {
    // Update the current top element of the stack
    state& t = states.back();
    t.opplan = op;
    t.quantity = qty;
    t.offset = o;
    t.level = lvl;
    first = false;
  }
  else
    // We need to create a new element on the stack
    states.push_back( state(op, qty, o, lvl) );
}


} // End namespace
