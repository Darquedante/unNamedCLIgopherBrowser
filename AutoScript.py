import subprocess

# Define the sequence of inputs
inputs = [
    '1\n',           # Connect to a Gopher server
    '1436.ninja\n',  # Server hostname
    '23\n',          # Selector '23'
    '9\n',           # Selector '9'
    'b\n'            # 'b' for back
]

# Convert the inputs list to a single string
input_sequence = ''.join(inputs)

# Run the gopher program and send the input sequence
process = subprocess.run(
    ['python', 'C:/Users/TUF505GT/gopher/gopherTESTING.py'],
    input=input_sequence,
    text=True,
    capture_output=True
)

# Print the output
print(process.stdout)
