# Task c02-t18

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Input object: m holds an object, key a string. Output object: value, the stored entry when the key is present (even when it is empty, zero or null), otherwise the configured default 'n/a' from spec.json. compute.py holds the defect. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
