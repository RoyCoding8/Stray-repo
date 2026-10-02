# Task c02-t08

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Input object: readings holds a list of {"v", "u"} records, want names the target unit. Unit table: cm=10, m=1000, mm=1.

Two stages collaborate: producer.py converts each reading to base units, consumer.py converts base units to the wanted unit rounded half-up to two decimals and flags each value. Flags use [1, 20] with both ends inclusive (low below, high above, ok otherwise). Output object: values then flags. A conversion that looks right on round numbers but rounds half-cases the other way, or that excludes the upper bound, fails the graded outputs. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
