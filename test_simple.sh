#!/bin/bash

echo "Test 1"
kubectl-smart diag pod non-existent-pod-xyz -n default >/dev/null 2>&1
echo "Exit code: $?"

echo "Test 2"
kubectl-smart --help >/dev/null 2>&1
echo "Exit code: $?"

echo "Test 3"
echo "This should print"

echo "DONE - script completed"