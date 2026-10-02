# Task c02-t05

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Names and tags travel with instrument readings that must be converted and flagged. Input object: names holds a list of strings, tags a list of strings, readings a list of {"v", "u"} records with unit s or m, want names the target unit.

names.py must strip surrounding whitespace then lowercase each string in order; tags.py must remove duplicates and sort what remains; pconv.py must convert each reading into the wanted unit and round half-up to two decimals; cconv.py must flag each converted value against [0, 5] with both ends inclusive (low below, high above, ok otherwise). app.py assembles names, tags, values and flags. The conversion pair shares one rounding and boundary convention: both halves must agree. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
