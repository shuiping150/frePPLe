#
# Process this file with automake to produce Makefile.in
#

AM_CPPFLAGS=-DDATADIRECTORY='"${pkgdatadir}"' -DLIBDIRECTORY='"${libdir}"' -DSYSCONFDIRECTORY='"${sysconfdir}/frepple"'

CLEANFILES = *.gcda *.gcov *.gcno

noinst_LTLIBRARIES = libutils.la
libutils_la_SOURCES = pythonutils.cpp date.cpp xmlparser.cpp actions.cpp library.cpp name.cpp
