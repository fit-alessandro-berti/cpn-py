from abc import ABC, abstractmethod
from typing import Any, Dict, List


# -----------------------------------------------------------------------------------
# ColorSets with Timed Support
# -----------------------------------------------------------------------------------

class ColorSet(ABC):
    def __init__(self, timed: bool = False, name: str = None):
        self.timed = timed
        self.name = name  # name will be assigned later by the parser if not provided

    @abstractmethod
    def is_member(self, value: Any) -> bool:
        pass

    def __repr__(self):
        # Default representation if not overridden
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}ColorSet{timed_str}"


class IntegerColorSet(ColorSet):
    def is_member(self, value: Any) -> bool:
        return isinstance(value, int)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}IntegerColorSet{timed_str}"


class RealColorSet(ColorSet):
    def is_member(self, value: Any) -> bool:
        return isinstance(value, float)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}RealColorSet{timed_str}"


class StringColorSet(ColorSet):
    def is_member(self, value: Any) -> bool:
        return isinstance(value, str)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}StringColorSet{timed_str}"


class BoolColorSet(ColorSet):
    def is_member(self, value: Any) -> bool:
        return isinstance(value, bool)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}BoolColorSet{timed_str}"


class UnitColorSet(ColorSet):
    """
    A 'unit' type often represents a single, trivial value (e.g. () in some languages).
    For membership, we can check for exactly () or any other convention as needed.
    """
    def is_member(self, value: Any) -> bool:
        return value == ()

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}UnitColorSet{timed_str}"


class IntInfColorSet(ColorSet):
    """
    'intinf' is often used to denote arbitrary-precision integers.
    In Python 3, all ints are arbitrary precision, so this is effectively the same as IntegerColorSet.
    """
    def is_member(self, value: Any) -> bool:
        return isinstance(value, int)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}IntInfColorSet{timed_str}"


class TimeColorSet(ColorSet):
    """
    'time' could be interpreted in various ways.
    Here we simply check if it's a numeric type (e.g., float or int) representing a time or timestamp.
    Adjust logic as needed for real usage (e.g., Python datetime).
    """
    def is_member(self, value: Any) -> bool:
        return isinstance(value, float) or isinstance(value, int)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}TimeColorSet{timed_str}"


class EnumeratedColorSet(ColorSet):
    def __init__(self, values: List[str], timed: bool = False, name: str = None):
        super().__init__(timed=timed, name=name)
        self.values = values

    def is_member(self, value: Any) -> bool:
        return value in self.values

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        values_str = ", ".join(repr(v) for v in self.values)
        return f"{name_str}EnumeratedColorSet({{{values_str}}}){timed_str}"


class ProductColorSet(ColorSet):
    def __init__(self, cs1: ColorSet, cs2: ColorSet, timed: bool = False, name: str = None):
        super().__init__(timed=timed, name=name)
        self.cs1 = cs1
        self.cs2 = cs2

    def is_member(self, value: Any) -> bool:
        if not isinstance(value, tuple) or len(value) != 2:
            return False
        return self.cs1.is_member(value[0]) and self.cs2.is_member(value[1])

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}ProductColorSet({repr(self.cs1)}, {repr(self.cs2)}){timed_str}"


class DictionaryColorSet(ColorSet):
    """
    A color set that checks membership for Python dictionaries.
    Modify if you specifically want 'frozenset'-like behavior
    or further constraints on keys/values.
    """
    def is_member(self, value: Any) -> bool:
        return isinstance(value, dict)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}DictionaryColorSet{timed_str}"

class RecordColorSet(ColorSet):
    """
    A color set for records, where each field has a name and an associated color set.
    """

    def __init__(self, field_types: List[tuple], timed: bool = False, name: str = None):
        super().__init__(timed=timed, name=name)
        self.field_types = field_types  # List of (field_name, ColorSet)

    def is_member(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        for field_name, cs in self.field_types:
            if field_name not in value or not cs.is_member(value[field_name]):
                return False
        return True

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        fields_str = ", ".join(f"{name}: {repr(cs)}" for name, cs in self.field_types)
        return f"{name_str}RecordColorSet({{{fields_str}}}){timed_str}"


class ListColorSet(ColorSet):
    """
    A color set for lists, where each element must be a member of the underlying color set.
    For "list int", we'd parse the underlying type and store it here.
    """
    def __init__(self, element_cs: ColorSet, timed: bool = False, name: str = None):
        super().__init__(timed=timed, name=name)
        self.element_cs = element_cs

    def is_member(self, value: Any) -> bool:
        if not isinstance(value, list):
            return False
        return all(self.element_cs.is_member(elem) for elem in value)

    def __repr__(self):
        timed_str = " timed" if self.timed else ""
        name_str = f"{self.name + ' ' if self.name else ''}"
        return f"{name_str}ListColorSet({repr(self.element_cs)}){timed_str}"


# -----------------------------------------------------------------------------------
# ColorSetParser with Timed Support
# -----------------------------------------------------------------------------------
class ColorSetParser:
    def __init__(self):
        self.colorsets: Dict[str, ColorSet] = {}

    def parse_definitions(self, text: str) -> Dict[str, ColorSet]:
        lines = text.strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            self._parse_line(line)
        return self.colorsets

    def _parse_line(self, line: str):
        if not line.endswith(";"):
            raise ValueError("Color set definition must end with a semicolon.")
        line = line[:-1].strip()  # remove trailing ";"
        if not line.startswith("colset "):
            raise ValueError("Color set definition must start with 'colset'.")
        line = line[len("colset "):].strip()
        parts = line.split("=", 1)
        if len(parts) != 2:
            raise ValueError("Invalid color set definition format.")
        name = parts[0].strip()
        type_str = parts[1].strip()

        # Check for "timed" keyword at the end
        timed = False
        if type_str.endswith("timed"):
            timed = True
            type_str = type_str[:-5].strip()

        cs = self._parse_type(type_str, timed)
        cs.name = name  # Assign the parsed name to the colorset
        self.colorsets[name] = cs

    def _parse_type(self, type_str: str, timed: bool) -> ColorSet:
        # Check for enumerated type: { 'red', 'green', ... }
        if type_str.startswith("{") and type_str.endswith("}"):
            return self._parse_enumerated_type(type_str, timed)

        # Direct primitive types
        if type_str.lower() == "int":
            return IntegerColorSet(timed=timed)
        if type_str.lower() == "real":
            return RealColorSet(timed=timed)
        if type_str.lower() == "string":
            return StringColorSet(timed=timed)
        if type_str.lower() == "dict":
            return DictionaryColorSet(timed=timed)
        if type_str.lower() == "bool":
            return BoolColorSet(timed=timed)
        if type_str.lower() == "unit":
            return UnitColorSet(timed=timed)
        if type_str.lower() == "intinf":
            return IntInfColorSet(timed=timed)
        if type_str.lower() == "time":
            return TimeColorSet(timed=timed)

        # "list" type: "list int", "list bool", "list MyEnumeratedSet", etc.
        if type_str.startswith("list "):
            sub_type = type_str[len("list "):].strip()
            sub_cs = self._parse_type(sub_type, False)
            return ListColorSet(sub_cs, timed=timed)

        # Product type
        if type_str.startswith("product(") and type_str.endswith(")"):
            inner = type_str[len("product("):-1].strip()
            comma_index = self._find_comma_at_top_level(inner)
            if comma_index == -1:
                raise ValueError("Invalid product definition: must have two types separated by a comma.")
            type1_str = inner[:comma_index].strip()
            type2_str = inner[comma_index + 1:].strip()

            cs1 = self._parse_type(type1_str, False)
            cs2 = self._parse_type(type2_str, False)
            return ProductColorSet(cs1, cs2, timed=timed)

        # product without parentheses which is translated to RecordColorSet with fields _1, _2, ... : product int * string -> record _1:int * _2:string
        if type_str.startswith("product "):
            inner = type_str[len("product "):].strip()
            parts = inner.split("*")
            field_types = []
            for i, part in enumerate(parts):
                part = part.strip()
                field_name = f"_${i+1}"
                field_cs = self._parse_type(part, False)
                field_types.append((field_name, field_cs))
            return RecordColorSet(field_types, timed=timed)


        if type_str.startswith("record"):
            # parse things like record id:STRING * leave_at: TIME * ... [timed]
            fields_str = type_str[len("record"):].strip()
            fields_and_types = fields_str.split("*")
            field_types = []
            for field_def in fields_and_types:
                field_def = field_def.strip()
                if ":" not in field_def:
                    raise ValueError(f"Invalid record field definition: {field_def}")
                field_name, field_type_str = field_def.split(":", 1)
                field_name = field_name.strip()
                field_type_str = field_type_str.strip()
                field_cs = self._parse_type(field_type_str, False)
                field_types.append((field_name, field_cs))

            return RecordColorSet(field_types, timed=timed)


        # If it's referencing a previously-defined colorset
        if type_str in self.colorsets:
            base_cs = self.colorsets[type_str]
            # If current definition is timed, ensure the base is also timed
            base_cs.timed = base_cs.timed or timed
            return base_cs

        raise ValueError(f"Unknown type definition or reference: {type_str}")

    def _parse_enumerated_type(self, type_str: str, timed: bool) -> EnumeratedColorSet:
        # remove outer braces { ... }
        inner = type_str[1:-1].strip()
        if not inner:
            raise ValueError("Enumerated color set cannot be empty.")

        # Enumerations are separated by commas, we assume each value is quoted
        values = [v.strip() for v in inner.split(",")]
        parsed_values = []
        for val in values:
            if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
                parsed_values.append(val[1:-1])
            else:
                raise ValueError(f"Enumerated values must be quoted strings. Invalid value: {val}")

        return EnumeratedColorSet(parsed_values, timed=timed)

    def _find_comma_at_top_level(self, s: str) -> int:
        """
        Finds a comma that is not nested within parentheses.
        Returns the index of that comma or -1 if none is found at top level.
        """
        level = 0
        for i, ch in enumerate(s):
            if ch == '(':
                level += 1
            elif ch == ')':
                level -= 1
            elif ch == ',' and level == 0:
                return i
        return -1


if __name__ == "__main__":
    parser = ColorSetParser()

    definitions = """
    colset Colors = { 'red', 'green' } timed;
    colset SimpleColors = { 'blue', 'yellow' };
    colset MyInts = int;
    colset MyReals = real;
    colset MyDict = dict;
    colset MyBools = bool timed;
    colset MyUnit = unit;
    colset MyBigInts = intinf;
    colset MyTime = time;
    colset MyListOfInts = list int;
    colset MyProduct = product(Colors, MyInts) timed;
    colset MyRecord = record id:MyInts * items: MyListOfInts timed;
    """

    parsed = parser.parse_definitions(definitions)
    for name, cs in parsed.items():
        print(f"{name} = {cs}")

    # Test membership
    print("\nTest membership:")
    print("Colors.is_member('red'):", parsed['Colors'].is_member('red'))
    print("Colors.is_member('blue'):", parsed['Colors'].is_member('blue'))
    print("SimpleColors.is_member('yellow'):", parsed['SimpleColors'].is_member('yellow'))
    print("MyInts.is_member(42):", parsed['MyInts'].is_member(42))
    print("MyInts.is_member('42'):", parsed['MyInts'].is_member('42'))
    print("MyReals.is_member(3.14):", parsed['MyReals'].is_member(3.14))
    print("MyReals.is_member('3.14'):", parsed['MyReals'].is_member('3.14'))
    print("MyDict.is_member({'key': 'value'}):", parsed['MyDict'].is_member({'key': 'value'}))
    print("MyDict.is_member(42):", parsed['MyDict'].is_member(42))
    print("MyBools.is_member(True):", parsed['MyBools'].is_member(True))
    print("MyBools.is_member('True'):", parsed['MyBools'].is_member('True'))
    print("MyUnit.is_member(()):", parsed['MyUnit'].is_member(()))
    print("MyUnit.is_member('not-unit'):", parsed['MyUnit'].is_member('not-unit'))
    print("MyBigInts.is_member(9999999999999999999999):", parsed['MyBigInts'].is_member(9999999999999999999999))
    print("MyTime.is_member(10.5):", parsed['MyTime'].is_member(10.5))
    print("MyTime.is_member('nope'):", parsed['MyTime'].is_member('nope'))

    # List test
    print("MyListOfInts.is_member([1,2,3]):", parsed['MyListOfInts'].is_member([1,2,3]))
    print("MyListOfInts.is_member(['1','2','3']):", parsed['MyListOfInts'].is_member(['1','2','3']))

    # Product test
    print("MyProduct.is_member(('red', 10)):", parsed['MyProduct'].is_member(('red', 10)))
    print("MyProduct.is_member(('red', 'notint')):", parsed['MyProduct'].is_member(('red', 'notint')))

    # Record test
    print("MyRecord.is_member({'id': 1, 'items': [1,2,3]}):", parsed['MyRecord'].is_member({'id': 1, 'items': [1,2,3]}))
