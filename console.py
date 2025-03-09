#!/usr/bin/env python3

import sys
import code
import inspect
import compiler
import readline
import atexit
import os

class CircuitConsole(code.InteractiveConsole):
    def __init__(self, circuits):
        super().__init__(locals=circuits)
        self.current_circuit = None
        self.current_func = None
        self.inputs = {}
        self.state = None
        
        # Set up readline history
        self.histfile = os.path.join(os.getcwd(), ".crash_history")
        try:
            readline.read_history_file(self.histfile)
        except FileNotFoundError:
            pass
        atexit.register(readline.write_history_file, self.histfile)
    
    def runsource(self, source, filename="<input>", symbol="single"):
        source = source.strip()
        if source.startswith("@"):
            func_name = source[1:]
            if func_name in self.locals:
                # Get the original function object
                func = self.locals[func_name]
                # Get input argument names from signature, excluding 'state'
                sig = inspect.signature(func)
                self.inputs = {name: 0 for name in sig.parameters if name != 'state'}
                # Store the raw circuit function
                self.current_circuit = func
                self.state = None
                self.current_func = func_name
                # Show initial state
                self._display_state()
            else:
                print(f"Unknown circuit: {func_name}")
            return False
            
        elif source in self.inputs:
            if self.current_circuit:
                # Toggle the input
                self.inputs[source] = 1 - self.inputs[source]
                # Run circuit with current inputs
                result = self._trigger_circuit()
                # Format inputs and outputs
                inputs_str = ", ".join(f"{k}={v}" for k, v in self.inputs.items())
                func = self.locals[self.current_func]
                if isinstance(result, tuple):
                    outputs_str = ", ".join(f"{name}={value}" for name, value in zip(func.output_names, result))
                else:
                    outputs_str = f"{func.output_names[0]}={result}"
                print(f"{{{inputs_str}}} -> {{{outputs_str}}}")
            else:
                print("No circuit selected. Use @<func> to select a circuit.")
            return False
            
        return super().runsource(source, filename, symbol)
    
    def _trigger_circuit(self):
        input_values = [self.inputs[name] for name in self.inputs]
        result, self.state = self.current_circuit(*(input_values + [self.state]))
        return result
    
    def _display_state(self):
        print(f"\nCircuit: {self.current_func}")
        inputs_str = ", ".join(f"{k}={v}" for k, v in self.inputs.items())
        print(f"{{{inputs_str}}} -> {{...}}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python console.py <crashscript file>")
        sys.exit(1)
        
    # Load and compile the circuit
    with open(sys.argv[1]) as f:
        code = f.read()
    tree, parts = compiler.parse_script(code)
    circuits = compiler.exec_tree(tree, parts)
    
    # Start the interactive console
    console = CircuitConsole(circuits)
    console.interact(banner="Circuit REPL")

if __name__ == "__main__":
    main()
