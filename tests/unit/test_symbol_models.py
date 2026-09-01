from parser_engine import (
    ExtractedClassSymbol as ClassSymbol,
    ExtractedFunctionSymbol as FunctionSymbol,
    ExtractedModuleSymbol as ModuleSymbol,
    Parameter,
    SymbolExtractor,
)


def test_symbol_hierarchy_exposes_shared_fields():
    module = ModuleSymbol(
        id="module_1",
        name="sample",
        lineStart=1,
        lineEnd=4,
        docstring="module doc",
        generatedSummary="",
        filePath="sample.py",
    )
    cls = ClassSymbol(
        id="class_1",
        name="Child",
        lineStart=2,
        lineEnd=4,
        docstring="class doc",
        generatedSummary="",
        parentClass="Base",
    )
    fn = FunctionSymbol(
        id="function_1",
        name="run",
        lineStart=3,
        lineEnd=4,
        docstring="function doc",
        generatedSummary="",
        parameters=(Parameter(name="x", type="int"),),
        returnType="int",
        owner="module",
    )

    assert module.generatedSummary == ""
    assert cls.generatedSummary == ""
    assert fn.generatedSummary == ""
    assert module.symbol_type == "module"
    assert cls.symbol_type == "class"
    assert fn.symbol_type == "function"
    assert fn.parameters[0].name == "x"

