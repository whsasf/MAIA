#!/bin/bash

TEST_HARNESS_DIR=`dirname $0`
CURRDIR=`pwd`

if [ "$PYTHON_HOME" = "" ] 
then
    echo "PYTHON_HOME not set"
    echo "Set \"PYTHON_HOME\" environment variable and try again."
    exit 2
fi

if [ \! -f ${TEST_HARNESS_DIR}/properties/sams.properties ]
then
  echo "${TEST_HARNESS_DIR}/properties/sams.properties not found"
  exit 2
fi
SAMS_CONFIG_FILE=${TEST_HARNESS_DIR}/properties/sams.properties

if [ \! -f ${TEST_HARNESS_DIR}/setclasspath.sh ]
then
    echo "${TEST_HARNESS_DIR}/setclasspath.sh not found"
    echo "Run \"ant buildjar\" and try again"
    exit 2
fi

cd ${TEST_HARNESS_DIR}

ENVCP=$CLASSPATH
. ${TEST_HARNESS_DIR}/setclasspath.sh

if [ ! -z "$ENVCP" ]; then
  CLASSPATH=$CLASSPATH:$ENVCP
fi

# Use environment variables "$JAVA_HOME" or "$JRE_HOME"
if [ ! -z "$JAVA_HOME" ]; then
  if [ ! -x "$JAVA_HOME"/bin/java ]; then
    echo "The JAVA_HOME environment variable is not defined correctly"
    cd ${CURRDIR}
    exit 1
  fi
  _RUNJAVA="$JAVA_HOME"/bin/java
  echo "Using JAVA_HOME: $JAVA_HOME"

else
  if [ -z "$JRE_HOME" ]; then
    if [ ! -x "$JRE_HOME"/bin/java ]; then
      echo "The JRE_HOME environment variable is not defined correctly"
      cd ${CURRDIR}
      exit 1
    fi
    _RUNJAVA="$JRE_HOME"/bin/java
    echo "Using JRE_HOME: $JRE_HOME"
  else
    _RUNJAVA="java"
  fi
fi

# Setup our own temporary directory to avoid issues accessing temp files across partitions
if [ ! -d ${TEST_HARNESS_DIR}/tmp ]; then
    mkdir "${TEST_HARNESS_DIR}/tmp"
fi

UNAME=`uname`
if [ "$UNAME" = "Linux" ]; then
	NATIVE_LIBS="-Djava.library.path=${TEST_HARNESS_DIR}/libs"
    NATIVE_TOOLS="-Dcp.tools.path=${TEST_HARNESS_DIR}/tools/linux"
elif [ "$UNAME" = "SunOS" ]; then
	NATIVE_LIBS="-Djava.library.path=${TEST_HARNESS_DIR}/libs"
    NATIVE_TOOLS="-Dcp.tools.path=${TEST_HARNESS_DIR}/tools/sparc"
else
	# Best guess
	NATIVE_LIBS="-Djava.library.path=${TEST_HARNESS_DIR}/libs/$UNAME"
    NATIVE_TOOLS="-Dcp.tools.path=${TEST_HARNESS_DIR}/tools/$UNAME"
fi

# Enable HTTP client logging if required
#HTTP_LOGGING="-Dorg.apache.commons.logging.Log=org.apache.commons.logging.impl.SimpleLog -Dorg.apache.commons.logging.simplelog.showdatetime=true -Dorg.apache.commons.logging.simplelog.log.org.apache.http=DEBUG -Dorg.apache.commons.logging.simplelog.log.org.apache.http.wire=DEBUG"


echo $_RUNJAVA "$HTTP_LOGGING -Djava.io.tmpdir=${TEST_HARNESS_DIR}/tmp" "-Dfile.encoding=UTF-8" "$NATIVE_LIBS" "$NATIVE_TOOLS" "-Dpython.home=$PYTHON_HOME" "-Djavax.sams.config.file=$SAMS_CONFIG_FILE" -classpath "$CLASSPATH:${TEST_HARNESS_DIR}/properties" net.cp.MobileTest.harness.Harness $*
$_RUNJAVA $HTTP_LOGGING "-Djava.io.tmpdir=${TEST_HARNESS_DIR}/tmp" "-Dfile.encoding=UTF-8" "$NATIVE_LIBS" "$NATIVE_TOOLS" "-Dpython.home=$PYTHON_HOME" "-Djavax.sams.config.file=$SAMS_CONFIG_FILE" -classpath "$CLASSPATH:${TEST_HARNESS_DIR}/properties" net.cp.MobileTest.harness.Harness $*

cd ${CURRDIR}
