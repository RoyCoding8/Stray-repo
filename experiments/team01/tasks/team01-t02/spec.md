# Task team01-t02

Program ABI: read one JSON object from the request file given as the first command-line argument, write one JSON object to the response file given as the second argument.

Input object: Texts holds a list of strings, Numbers a list of numbers.

The program must drop duplicate strings, then sort the survivors, in order, and place the result under Texts. It must subtract the smallest number from the largest (0 for an empty list), and place the result under Numbers.

Both halves are required: a correct answer transforms the texts and aggregates the numbers together.
