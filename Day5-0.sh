### Fibonacci sequence: Write a shell script that generates the first n Fibonacci numbers.
    # Base Cases:
    #   F(0) = 0
    #   F(1) = 1
    # Recursive Case:
    #   F(n) = F(n-1) + F(n-2) for n > 1


#!/bin/bash

function fibonacci {
    local n=$1
    local a=0
    local b=1
    local output=""

    for (( i=0; i<n; i++ )); do
        output+="$a "
        ((a, b = b, a + b))
    done

    echo $output
}

# Check if the input argument is provided && is a non-negative integer
if [[ -z $1 || ! $1 =~ ^[0-9]+$ ]]; then
    echo "Error: Please provide a non-negative integer."
    exit 1
fi

fibonacci $1
