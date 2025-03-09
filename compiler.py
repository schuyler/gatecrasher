import sys
from ast import *
from pprint import pprint
from graphlib import TopologicalSorter
from types import SimpleNamespace as namespace

class StateTracker(NodeVisitor):
    def __init__(self):
        super().__init__()
        self.parts = {}
        self.graph = TopologicalSorter()

    def visit_FunctionDef(self, node):
        self.func = node.name
        self.args = tuple(arg.arg for arg in node.args.args)
        self.returns = ()
        self.vars = set()
        self.deps = []

        if isinstance(node.returns, Tuple):
            self.returns = tuple(name.id for name in node.returns.elts)
        else:
            self.returns = (node.returns.id,)

        for nd in node.body:
            self.generic_visit(nd)

        self.parts[node.name] = {
            "args": self.args,
            "state": tuple(sorted(self.vars)),
            "deps": self.deps,
            "dep_state": (),
            "returns": self.returns,
            "stateful": bool(self.vars),
        }

    def visit_Name(self, node):
        if node.id not in self.args and isinstance(node.ctx, Load):
            self.vars.add(node.id)
        return node

    def visit_Call(self, node):
        self.deps.append(node.func.id)
        self.graph.add(self.func, node.func.id)
        for nd in node.args:
            self.visit(nd)
        return node
    
    def analyze(self):
        n = 0
        # Iterate over the parts in topological order
        for part_name in self.graph.static_order():
            part = self.parts[part_name]
            sub_states = []
            # Iterate over the dependencies of the part
            for dep_name in part["deps"]:
                dep = self.parts[dep_name]
                # If the dependency is stateful, add a new state variable
                if dep["stateful"]:
                    # Generate a unique state variable name based on the dependency name
                    dep_id = f"_{dep_name}_{n}"
                    sub_states.append(dep_id)
                    n += 1
                # Store the list of state variables for the part's dependencies
                part["dep_state"] = tuple(sub_states)
            # If the part has state or dependencies with state, mark it as stateful
            if part["state"] or part["dep_state"]:
                part["stateful"] = True

class RewriteDeclarations(NodeTransformer):
    def __init__(self, parts):
        super().__init__()
        self.parts = parts

    def _unpack_state(self, vars, parts):
        # Generate an assign statement to unpack the state variables
        state_vars = ", ".join(vars + parts)
        default_vals = ["0"] * len(vars) + ["None"] * len(parts)
        stmt = f"{state_vars} = state if state else ({', '.join(default_vals)})"
        return parse(stmt).body[0]

    def _pack_state(self, vars, parts):
        # Generate a return statement to re-pack the state variables
        state_vars = ", ".join(vars + parts)
        return parse(f"state = ({state_vars})").body[0]

    def _stateful_return(self, returns):
        # Generate a return statement to return the output and state
        return_vars = ", ".join(returns)
        return parse(f"return ({return_vars}), state").body[0]

    def visit_FunctionDef(self, node):
        self.part = self.parts[node.name]
        self.calls = list(self.part["dep_state"])

        self.generic_visit(node)

        p = namespace(self.parts[node.name])
        if p.stateful:
            # Add state argument to function
            node.args.args.append(arg(arg="state"))
            # Add default value for state argument
            node.args.defaults.append(Constant(value=None))
            # Unpack state argument at the beginning of the function
            pack = self._pack_state(p.state, p.dep_state)
            # Pack state argument at the end of the function
            unpack = self._unpack_state(p.state, p.dep_state)
            # Add unpack and pack to the function body
            node.body = [unpack] + node.body + [pack]

        # Delete the "return type" of the function
        if node.returns:
            return_value = node.returns
            del node.returns

            if p.stateful:
                # Add the state variable to the return statement
                return_node = self._stateful_return(p.returns)
            else:
                # Add the return statement to the end of the function body
                return_node = Return(value=return_value)

            # Add the return statement to the end of the function body
            node.body.append(return_node)

        fix_missing_locations(node)
        return node
    
    def visit_Assign(self, node):
        self.generic_visit(node)

        if isinstance(node.value, Call):
            targets, call = node.targets, node.value
            if self.parts[call.func.id].get("state"):
                # Get the next state variable
                part_state = self.calls.pop(0)
                # Add the next state variable to the function return assignment
                original_target = targets[0]
                targets[0] = Tuple(elts=[original_target, Name(id=part_state, ctx=Store())], ctx=Store())
                # Add the next state variable to the end of the function call
                call.args.append(Name(id=part_state, ctx=Load()))

        return node

def parse_script(fn_def):
    tree = parse(fn_def)
    tracker = StateTracker()
    tracker.visit(tree)
    tracker.analyze()
    rewriter = RewriteDeclarations(tracker.parts)
    rewriter.visit(tree)
    return tree, tracker.parts

def exec_tree(tree, parts):
    defs = {"__builtins__": {}}
    code = compile(tree, filename="<ast>", mode="exec")
    exec(code, defs)
    # Attach output names to each function
    for name, part in parts.items():
        if name in defs:
            defs[name].output_names = part["returns"]
    return defs

def build(fn):
    state = None
    def wrapper(*args):
        nonlocal state
        args = args + (state,)
        output, state = fn(*args)
        return output
    return wrapper

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        fn_def = f.read()
    print("\nTransformed Python code:\n" + "-"*30 + "\n")
    tree, parts = parse_script(fn_def)
    print(unparse(tree))

    print("\nCompiled Python functions:\n" + "-"*30 + "\n")
    defs = exec_tree(tree, parts)
    pprint(tuple(k for k in defs.keys() if not k.startswith("__")))
    print("\n")
