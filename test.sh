#!/usr/bin/env bash
TESTS=../depsolver/tests

echo Running make all...
make all
echo

echo Starting tests...
for test in `ls -d ${TESTS}/*/`;
do
    echo Running ${test}
    ( ulimit -t 300 -m 1000000 ; ./solve ${test}repository.json ${test}initial.json ${test}constraints.json > commands.json )
    ${TESTS}/judge.py ${test}/repository.json ${test}/initial.json commands.json ${test}/constraints.json
    # read -n1 -r -p "Press any key to continue..."  # pause
    echo
done

rm commands.json
