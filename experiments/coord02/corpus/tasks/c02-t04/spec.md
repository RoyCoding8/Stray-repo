# Task c02-t04

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Four record fields arrive together and leave together. Input object: names holds a list of strings, scores a list of numbers, tags a list of strings, values a list of numbers.

Each field has its own module and every module has a defect: names.py must strip surrounding whitespace then lowercase each string in order; scores.py must clamp each number into [0, 100] then round to two decimals; tags.py must remove duplicates and sort what remains; stats.py must report the mean of values rounded to two decimals, or 0 when values is empty. app.py assembles the four outputs under names, scores, tags and stat. Fixing only some modules cannot satisfy the graded outputs. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
