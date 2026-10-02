# Task c02-t29

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Input object: cells holds a list of {"v"} records, factor a number. The first stage scales each cell by factor rounded to two decimals; the second stage reports the rounded sum as total. Output object: values then total. This task answers to interface cellsum/1 only: similarly named stages from other interfaces do not apply here, while the same interface under unfamiliar stage names binds normally. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
