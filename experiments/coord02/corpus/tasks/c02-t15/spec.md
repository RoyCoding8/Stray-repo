# Task c02-t15

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Two stages collaborate and either stage may be at fault, so probe before repairing. detect.py must classify the payload: mode "b" when payload code is at least 5, else mode "a". operate.py must aggregate the list under the per-mode key of list_keys (convention v2) with the per-mode operation from {a=prod, b=sum}. Output object: mode then result. Run the program on small crafted inputs first: an input whose mode flips the expected aggregate tells you which stage to fix. Edge cases are graded: empty lists, zero and missing values, exact boundary values, and repeated entries must all be handled.
