# Task c02-t30

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Input object: parcels holds a list of {"v", "u"} records, want names the target unit. Unit table: p=40, q=1. Three unfamiliar stages collaborate: intake.py reads each parcel, convert.py converts to the wanted unit rounded half-up to two decimals, finalize.py flags each value against [0, 2] with both ends inclusive. This chain answers to interface cellchain/1 only: bindings written for other interfaces must be refused, even though the arithmetic resembles them. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
