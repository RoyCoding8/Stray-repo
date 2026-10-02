# Task team01-t05

Program ABI: read one JSON object from the request file given as the first command-line argument, write one JSON object to the response file given as the second argument.

Input object: Readings holds a list of value/unit pairs, Want names one unit.

Known units and their size in the shared base unit: cm=10, m=1000, mm=1.

The program must convert every reading into the shared base unit by multiplying with its unit size, then express each base value in the wanted unit by dividing by the wanted unit size rounded to two decimals, in order, under Values. Producer and consumer agree on base-unit values.
