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
        # Add help and list to the local namespace
        circuits['help'] = self.help
        circuits['?'] = self.help
        circuits['list'] = self.list_circuits
        
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

    def list_circuits(self):
        """Display all available circuits."""
        print("\nAvailable Circuits:")
        print("-----------------")
        for name, obj in self.locals.items():
            if callable(obj) and name not in ('help', '?', 'list'):
                print(f"@{name}")
        print()

    def help(self):
        """Display help information about using the Circuit REPL."""
        print("""
Circuit REPL Help:
-----------------
@<name>     Select a circuit by name (e.g., @and_gate)
<input>     Toggle an input value (0/1) for the current circuit
<enter>     Re-run the current circuit with existing inputs
list()      Display all available circuits

Examples:
    @nand       Select the nand circuit
    a           Toggle input 'a'
    b           Toggle input 'b'
    <enter>     Re-run with current inputs

Tips:
- The current state and inputs are shown after selecting a circuit
- Outputs are displayed automatically after each input toggle
- Use help() or ?() to show this message
""")
    
    def runsource(self, source, filename="<input>", symbol="single"):
        source = source.strip()
        if source in ('help', '?', 'list'):
            if source == 'list':
                self.list_circuits()
            else:
                self.help()
            return False
        elif not source and self.current_circuit:
            # Re-run circuit with current inputs on empty input
            _ = self._trigger_circuit()
            return False
        elif source.startswith("@"):
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
                # Run circuit with current inputs - outputs handled in _trigger_circuit
                _ = self._trigger_circuit()
            else:
                print("No circuit selected. Use @<func> to select a circuit.")
            return False
            
        return super().runsource(source, filename, symbol)
    
    def _trigger_circuit(self):
        input_values = [self.inputs[name] for name in self.inputs]
        MAX_ITERATIONS = 100  # Safety limit to prevent infinite loops
        iteration = 0
        prev_result = None

        while iteration < MAX_ITERATIONS:
            result, self.state = self.current_circuit(*(input_values + [self.state]))
            
            # Format outputs
            func = self.locals[self.current_func]
            if isinstance(result, tuple):
                outputs_str = ", ".join(f"{name}={value}" for name, value in zip(func.output_names, result))
            else:
                outputs_str = f"{func.output_names[0]}={result}"
            
            # Check for stabilization before printing
            if result == prev_result:
                break

            # Display with inputs only on first iteration, subsequent outputs indented
            if iteration == 0:
                inputs_str = ", ".join(f"{k}={v}" for k, v in self.inputs.items())
                full_line = f"{{{inputs_str}}} -> {{{outputs_str}}}"
                print(full_line)
                # Calculate padding based on actual input length
                self.arrow_padding = len(full_line) - len(f" -> {{{outputs_str}}}")
            else:
                print(f"{' ' * self.arrow_padding} -> {{{outputs_str}}}")

            prev_result = result
            iteration += 1

        return result
    
    def _display_state(self):
        print(f"Loaded: {self.current_func}")
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
    
    # Start the interactive console with help text
    console = CircuitConsole(circuits)
    console.help()
    console.interact(banner="")

if __name__ == "__main__":
    main()
