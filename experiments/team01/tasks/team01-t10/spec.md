# Task team01-t10

Program ABI: read one JSON object from the request file given as the first command-line argument, write one JSON object to the response file given as the second argument.

Input object: a request whose shape selects one of two aggregations.

First run the diagnostic: compare Code against 100: codes at or above it report mode B from Vals, lower codes mode A from Vals. Then take the smallest (0 when empty) for mode A and take the largest (0 when empty) for mode B, and report both the selected mode and its result.

The diagnostic observation decides the aggregation, so decide first and aggregate second.
