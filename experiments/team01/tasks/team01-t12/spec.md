# Task team01-t12

Program ABI: read one JSON object from the request file given as the first command-line argument, write one JSON object to the response file given as the second argument.

Input object: a request whose shape selects one of two aggregations.

First run the diagnostic: inspect the shape of Items: a mapping reports mode B over its values, a list reports mode A over its elements. Then multiply them for mode A and add them for mode B, and report both the selected mode and its result.

The diagnostic observation decides the aggregation, so decide first and aggregate second.
