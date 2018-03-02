@echo off

rem set PYTHON_HOME=C:\jython

IF "%PYTHON_HOME%"=="" (ECHO PYTHON_HOME not set.&ECHO Set "PYTHON_HOME" environment variable and try again.&GOTO:EOF)

IF NOT EXIST SETCLASSPATH.bat (ECHO SETCLASSPATH.bat not found.&ECHO Run "ant buildjar" and try again.&GOTO:EOF)

SETLOCAL

rem Use environment variables if set 
if not "%JAVA_HOME%" == "" goto gotJdkHome
if not "%JRE_HOME%" == "" goto gotJreHome
goto noJavaHome

:gotJreHome
if not exist "%JRE_HOME%\bin\java.exe" goto noJavaHome
set _RUNJAVA="%JRE_HOME%\bin\java"
echo Using JRE_HOME: %JRE_HOME%
goto finishedJavaHome

:gotJdkHome
if not exist "%JAVA_HOME%\bin\java.exe" goto noJavaHome
set _RUNJAVA="%JAVA_HOME%\bin\java"
echo Using JAVA_HOME: %JAVA_HOME%
goto finishedJavaHome

:noJavaHome
rem Rely on PATH
set _RUNJAVA=java

:finishedJavaHome

call SetClassPath.bat
set TEST_HARNESS_DIR=%~dp0

IF NOT EXIST %TEST_HARNESS_DIR%properties\sams.properties (ECHO %TEST_HARNESS_DIR%\properties\sams.properties not found.&GOTO:EOF)
set SAMS_CONFIG_FILE=%TEST_HARNESS_DIR%properties\sams.properties

set ARGS=

:loop
if [%1] == [] goto end
        set ARGS=%ARGS% %1
        shift
        goto loop
:end

set CLASSPATH=%CLASSPATH%;%TEST_HARNESS_DIR%properties

echo.
echo %_RUNJAVA% -Dfile.encoding=UTF-8 "-Djava.library.path=%TEST_HARNESS_DIR%libs\win32" "-Dcp.tools.path=%TEST_HARNESS_DIR%\tools\win32" "-Dpython.home=%PYTHON_HOME%" "-Dpython.path=%TEST_HARNESS_DIR%python2.1\Lib" -D"javax.sams.config.file=%SAMS_CONFIG_FILE%" -classpath "%CLASSPATH%" net.cp.MobileTest.harness.Harness %ARGS%
%_RUNJAVA% -Dfile.encoding=UTF-8 "-Djava.library.path=%TEST_HARNESS_DIR%libs\win32" "-Dcp.tools.path=%TEST_HARNESS_DIR%\tools\win32" "-Dpython.home=%PYTHON_HOME%" "-Dpython.path=%TEST_HARNESS_DIR%python2.1\Lib" -D"javax.sams.config.file=%SAMS_CONFIG_FILE%" -classpath "%CLASSPATH%" net.cp.MobileTest.harness.Harness %ARGS%

ENDLOCAL
:: End program
GOTO:EOF
