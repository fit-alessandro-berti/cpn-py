import importlib.util
import sys
from pathlib import Path

from cpnpy.cpn.cpn_imp import *
from cpnpy.simulation.simu import simulate_until_deadlock

def load_module_from_file(fullname: str, file_path: str):
    spec = importlib.util.spec_from_file_location(fullname, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {fullname} from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module  # important for imports to resolve
    spec.loader.exec_module(module)
    return module

def test_module_user_code():
    TEST_DIR = Path(__file__).resolve().parents[1]  # .../test
    sys.path.insert(0, str(TEST_DIR))

    user_code = load_module_from_file(
        "cpn.user_code.user_code",
        str(TEST_DIR / "cpn" / "user_code" / "user_code.py"),
    )


    cs_definitions = """
        colset INT = int timed;
        colset STRING = string;
        colset PAIR = product(INT, STRING) timed;
        """

    context = EvaluationContext(user_code=user_code)

    parser = ColorSetParser()
    colorsets = parser.parse_definitions(cs_definitions)

    int_set = colorsets["INT"]
    pair_set = colorsets["PAIR"]

    p_int = Place("P_Int", int_set)
    p_pair = Place("P_Pair", pair_set)

    t = Transition("T",
                   guard="x > 1",
                   variables=["x"], transition_delay=2)

    cpn = CPN()
    cpn.add_place(p_int)
    cpn.add_place(p_pair)

    cpn.add_transition(t)
    cpn.add_arc(Arc(p_int, t, "x"))
    cpn.add_arc(Arc(t, p_pair, "(square(x), 'str') @+1"))

    # Create a marking
    marking = Marking()
    marking.set_tokens("P_Int", [1, 2, 3])  # all at timestamp 0

    simulate_until_deadlock(cpn, marking, context)

    # check tokens in output place
    # print(marking.get_multiset("P_Int"))
    # print(marking.get_multiset("P_Pair"))
    assert marking.get_multiset("P_Int").tokens == [Token(1, timestamp=0)]
    assert marking.get_multiset("P_Pair").tokens == [Token((4, 'str'), timestamp=3), Token((9, 'str'), timestamp=3)]
    assert marking.global_clock == 3

    # from cpnpy.visualization.visualizer import CPNGraphViz
    # builder = CPNGraphViz()
    # builder.apply(cpn, marking)
    # builder.view()

if __name__ == '__main__':
    test_module_user_code()