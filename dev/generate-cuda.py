# BSD 3-Clause License; see https://github.com/scikit-hep/awkward-1.0/blob/master/LICENSE

import argparse
import ast
import copy
import os
import sys
from collections import OrderedDict

import yaml

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
KERNEL_WHITELIST = [
    "awkward_new_Identities",
    "awkward_Identities32_to_Identities64",
    "awkward_RegularArray_num",
    "awkward_ListOffsetArray_flatten_offsets",
    "awkward_IndexedArray_overlay_mask",
    "awkward_IndexedArray_mask",
    "awkward_ByteMaskedArray_mask",
    "awkward_zero_mask",
    "awkward_RegularArray_compact_offsets",
    "awkward_IndexedArray_fill_count",
    "awkward_UnionArray_fillna",
    "awkward_ListArray_min_range",
    "awkward_localindex",
    "awkward_content_reduce_zeroparents_64",
    "awkward_ListOffsetArray_reduce_global_startstop_64",
    "awkward_ListOffsetArray_reduce_nonlocal_maxcount_offsetscopy_64",
    "awkward_IndexedArray_reduce_next_fix_offsets_64",
    "awkward_Index8_to_Index64",
    "awkward_IndexU8_to_Index64",
    "awkward_Index32_to_Index64",
    "awkward_IndexU32_to_Index64",
    "awkward_carry_arange",
    "awkward_index_carry_nocheck",
    "awkward_NumpyArray_contiguous_init",
    "awkward_NumpyArray_getitem_next_array_advanced",
    "awkward_NumpyArray_getitem_next_at",
    "awkward_RegularArray_getitem_next_array_advanced",
    "awkward_UnionArray_regular_index_getsize",
    "awkward_ByteMaskedArray_toIndexedOptionArray",
    "awkward_ListOffsetArray_reduce_nonlocal_nextstarts_64",
    "awkward_combinations",
    "awkward_index_carry",
    "awkward_ByteMaskedArray_getitem_carry",
    # "awkward_IndexedArray_simplify", Fails on Python 3.5, 3.6 and 3.7
    "awkward_RegularArray_broadcast_tooffsets",
    "awkward_ListArray_validity",
    "awkward_UnionArray_validity",
]

KERNEL_CURIOUS = [
    "awkward_Identities_from_ListArray",
    "awkward_Identities_from_IndexedArray",
    "awkward_Identities_from_UnionArray",
    "awkward_index_rpad_and_clip_axis0",
    "awkward_RegularArray_rpad_and_clip_axis1",
    "awkward_ListArray_rpad_and_clip_length_axis1",
    "awkward_ListArray_localindex",
    "awkward_ByteMaskedArray_overlay_mask",
    "awkward_BitMaskedArray_to_ByteMaskedArray",
    "awkward_BitMaskedArray_to_IndexedOptionArray",
    "awkward_reduce_count_64",
    "awkward_reduce_countnonzero",
    "awkward_reduce_sum_int64_bool_64",
    "awkward_reduce_sum_int32_bool_64",
    "awkward_reduce_sum_bool",
    "awkward_reduce_prod_int64_bool_64",
    "awkward_reduce_prod_int32_bool_64",
    "awkward_reduce_prod_bool",
    "awkward_reduce_min",
    "awkward_reduce_max",
    "awkward_reduce_argmin",
    "awkward_reduce_argmax",
    "awkward_reduce_argmax_bool_64",
    "awkward_ListOffsetArray_reduce_nonlocal_nextshifts_64",
    "awkward_RegularArray_localindex",
    "awkward_NumpyArray_reduce_adjust_starts_64",
    "awkward_NumpyArray_reduce_adjust_starts_shifts_64",
    "awkward_NumpyArray_reduce_mask_ByteMaskedArray_64",
    "awkward_NumpyArray_contiguous_next",
    "awkward_NumpyArray_getitem_next_range",
    "awkward_NumpyArray_getitem_next_range_advanced",
    "awkward_NumpyArray_getitem_next_array",
    "awkward_Identities_getitem_carry",
    "awkward_RegularArray_getitem_next_range",
    "awkward_RegularArray_getitem_next_range_spreadadvanced",
    "awkward_RegularArray_getitem_next_array_regularize",
    "awkward_RegularArray_getitem_next_array",
    "awkward_RegularArray_getitem_carry",
    "awkward_RegularArray_getitem_jagged_expand",
    "awkward_ListArray_getitem_jagged_expand",
    "awkward_missing_repeat",
    "awkward_IndexedArray_validity",
]


def traverse(node, args={}, forflag=False, declared=[]):
    if node.__class__.__name__ == "For":
        if len(node.iter.args) == 1:
            code = "if (thread_id < {0}) {{\n".format(traverse(node.iter.args[0]))
        elif len(node.iter.args) == 2:
            code = "if ((thread_id < {0}) && (thread_id >= {1})) {{\n".format(
                traverse(node.iter.args[1]), traverse(node.iter.args[0])
            )
        else:
            raise Exception("Unable to handle Python for loops with >2 args")
        for subnode in node.body:
            code += traverse(subnode, args, True, declared)
        code += "}\n"
    elif node.__class__.__name__ == "While":
        assert node.test.__class__.__name__ == "Compare"
        assert len(node.test.ops) == 1
        code = "while ({0}) {{\n".format(traverse(node.test))
        for subnode in node.body:
            code += traverse(subnode, args, True, declared)
        code += "}\n"
    elif node.__class__.__name__ == "Raise":
        if sys.version_info[0] == 2:
            code = 'err->str = "{0}";\n'.format(node.type.args[0].s)
        elif sys.version_info[0] == 3 and sys.version_info[1] in [5, 6, 7]:
            code = 'err->str = "{0}";\n'.format(node.exc.args[0].s)
        else:
            code = (
                'err->str = "{0}";\n'.format(node.exc.args[0].value)
                + 'err->filename = "FILENAME(__LINE__)";\nerr->pass_through=true;\n'
            )
    elif node.__class__.__name__ == "If":
        code = ""
        tempdeclared = copy.copy(declared)
        for subnode in node.body:
            traverse(subnode, args, forflag, declared)
        todecl = set(tempdeclared) ^ set(declared)
        for todeclarg in todecl:
            code += "int64_t {0};\n".format(todeclarg)
        code += "if ({0}) {{\n".format(traverse(node.test, args, forflag, declared))
        for subnode in node.body:
            code += " " * 2 + traverse(subnode, args, forflag, declared) + "\n"
        code += "} else {\n"
        for subnode in node.orelse:
            code += " " * 2 + traverse(subnode, args, forflag, declared) + "\n"
        code += "}\n"
    elif node.__class__.__name__ == "Name":
        if forflag and node.id == "i":
            code = "thread_id"
        else:
            code = node.id
    elif node.__class__.__name__ == "Num":
        code = str(node.n)
    elif node.__class__.__name__ == "BinOp":
        left = traverse(node.left, args, forflag, declared)
        right = traverse(node.right, args, forflag, declared)
        if left == "i":
            left = "thread_id"
        if right == "i":
            right = "thread_id"
        code = "({0} {1} {2})".format(
            left, traverse(node.op, args, forflag, declared), right,
        )
    elif node.__class__.__name__ == "UnaryOp":
        if node.op.__class__.__name__ == "USub":
            if sys.version_info[0] == 3 and sys.version_info[1] in [5, 6, 7]:
                code = "-{0}".format(node.operand.n)
            else:
                code = "-{0}".format(node.operand.value)
    elif node.__class__.__name__ == "Sub":
        code = "-"
    elif node.__class__.__name__ == "Add":
        code = "+"
    elif node.__class__.__name__ == "Mult":
        code = "*"
    elif node.__class__.__name__ == "Subscript":
        if node.slice.value.__class__.__name__ == "Name" and node.slice.value.id == "i":
            code = node.value.id + "[thread_id]"
        elif (
            node.slice.value.__class__.__name__ == "Constant"
            or node.slice.value.__class__.__name__ == "BinOp"
            or node.slice.value.__class__.__name__ == "Subscript"
            or node.slice.value.__class__.__name__ == "Name"
            or node.slice.value.__class__.__name__ == "Num"
        ) and hasattr(node.value, "id"):
            code = (
                node.value.id
                + "["
                + traverse(node.slice.value, args, forflag, declared)
                + "]"
            )
        elif node.value.__class__.__name__ == "Subscript":
            code = (
                traverse(node.value.value)
                + "["
                + traverse(node.value.slice.value)
                + "]["
                + traverse(node.slice.value)
                + "]"
            )
        else:
            code = traverse(node.slice.value, args, forflag, declared)
    elif node.__class__.__name__ == "Call":
        assert len(node.args) == 1
        code = "({0})({1})".format(
            node.func.id, traverse(node.args[0], args, forflag, declared)
        )
    elif node.__class__.__name__ == "Constant":
        if node.value == True:
            code = "true"
        elif node.value == False:
            code = "false"
        else:
            code = node.value
    elif node.__class__.__name__ == "Compare":
        if len(node.ops) == 1 and node.ops[0].__class__.__name__ == "Lt":
            code = "({0} < {1})".format(
                traverse(node.left, args, forflag, declared),
                traverse(node.comparators[0], args, forflag, declared),
            )
        elif len(node.ops) == 1 and node.ops[0].__class__.__name__ == "NotEq":
            code = "({0} != {1})".format(
                traverse(node.left, args, forflag, declared),
                traverse(node.comparators[0], args, forflag, declared),
            )
        elif len(node.ops) == 1 and node.ops[0].__class__.__name__ == "Eq":
            code = "({0} == {1})".format(
                traverse(node.left, args, forflag, declared),
                traverse(node.comparators[0], args, forflag, declared),
            )
        elif len(node.ops) == 1 and node.ops[0].__class__.__name__ == "Gt":
            code = "({0} > {1})".format(
                traverse(node.left, args, forflag, declared),
                traverse(node.comparators[0], args, forflag, declared),
            )
        elif len(node.ops) == 1 and node.ops[0].__class__.__name__ == "GtE":
            code = "({0} >= {1})".format(
                traverse(node.left, args, forflag, declared),
                traverse(node.comparators[0], args, forflag, declared),
            )
        else:
            raise Exception(
                "Unhandled Compare node {0}. Please inform the developers.".format(
                    node.ops[0]
                )
            )
    elif node.__class__.__name__ == "Assign":
        assert len(node.targets) == 1
        left = traverse(node.targets[0], args, forflag, declared)
        if "[" in left:
            left = left[: left.find("[")]
        code = ""
        if left not in args.keys() and ("*" + left) not in args.keys():
            flag = True
        else:
            flag = False
        if node.value.__class__.__name__ == "Name" and node.value.id == "i":
            code = ""
            if flag and (
                traverse(node.targets[0], args, forflag, declared) not in declared
            ):
                code += "auto "
                declared.append(traverse(node.targets[0], args, forflag, declared))
            code += "{0} = thread_id;\n".format(
                traverse(node.targets[0], args, forflag, declared)
            )
        else:
            if node.value.__class__.__name__ == "IfExp":
                if flag and (
                    traverse(node.targets[0], args, forflag, declared) not in declared
                ):
                    code = "auto {0} = {1};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.orelse, args, forflag, declared),
                    )
                    declared.append(traverse(node.targets[0], args, forflag, declared))
                code += "if ({0}) {{\n {1} = {2};\n }} else {{\n {1} = {3};\n }}\n".format(
                    traverse(node.value.test, args, forflag, declared),
                    traverse(node.targets[0], args, forflag, declared),
                    traverse(node.value.body, args, forflag, declared),
                    traverse(node.value.orelse, args, forflag, declared),
                )
            elif node.value.__class__.__name__ == "Compare":
                code = ""
                if flag and (
                    traverse(node.targets[0], args, forflag, declared) not in declared
                ):
                    code += "auto "
                    declared.append(traverse(node.targets[0], args, forflag, declared))
                if (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Lt"
                ):
                    code += "{0} = {1} < {2};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Gt"
                ):
                    code += "{0} = {1} > {2};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "GtE"
                ):
                    code += "{0} = {1} >= {2};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "NotEq"
                ):
                    code += "{0} = {1} != {2};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Eq"
                ):
                    code += "{0} = {1} == {2};\n".format(
                        traverse(node.targets[0], args, forflag, declared),
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                else:
                    raise Exception(
                        "Unhandled Compare node {0}. Please inform the developers.".format(
                            node.value.ops[0]
                        )
                    )
            else:
                code = ""
                if flag and (
                    traverse(node.targets[0], args, forflag, declared) not in declared
                ):
                    code += "auto "
                    declared.append(traverse(node.targets[0], args, forflag, declared))
                code += "{0} = {1};\n".format(
                    traverse(node.targets[0], args, forflag, declared),
                    traverse(node.value, args, forflag, declared),
                )
    elif node.__class__.__name__ == "AugAssign":
        if node.op.__class__.__name__ == "Add":
            operator = "+="
        else:
            raise Exception(
                "Unhandled AugAssign node {0}".format(node.op.__class__.__name__)
            )
        left = traverse(node.target, args, forflag, declared)
        if "[" in left:
            left = left[: left.find("[")]
        code = ""
        if left not in args.keys() and ("*" + left) not in args.keys():
            flag = True
        else:
            flag = False
        if node.value.__class__.__name__ == "Name" and node.value.id == "i":
            code = ""
            if flag and (
                traverse(node.target, args, forflag, declared) not in declared
            ):
                code += "auto "
                declared.append(traverse(node.target, args, forflag, declared))
            code += "{0} = thread_id;\n".format(
                traverse(node.target, args, forflag, declared)
            )
        else:
            if node.value.__class__.__name__ == "IfExp":
                if flag and (
                    traverse(node.target, args, forflag, declared) not in declared
                ):
                    code = "auto {0} {1} {2};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.orelse, args, forflag, declared),
                    )
                    declared.append(traverse(node.target, args, forflag, declared))
                code += "if ({0}) {{\n {1} {2} {3};\n }} else {{\n {1} {2} {4};\n }}\n".format(
                    traverse(node.value.test, args, forflag, declared),
                    traverse(node.target, args, forflag, declared),
                    operator,
                    traverse(node.value.body, args, forflag, declared),
                    traverse(node.value.orelse, args, forflag, declared),
                )
            elif node.value.__class__.__name__ == "Compare":
                code = ""
                if flag and (
                    traverse(node.target, args, forflag, declared) not in declared
                ):
                    code += "auto "
                    declared.append(traverse(node.target, args, forflag, declared))
                if (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Lt"
                ):
                    code += "{0} {1} {2} < {3};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Gt"
                ):
                    code += "{0} {1} {2} > {3};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "GtE"
                ):
                    code += "{0} {1} {2} >= {3};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "NotEq"
                ):
                    code += "{0} {1} {2} != {3};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                elif (
                    len(node.value.ops) == 1
                    and node.value.ops[0].__class__.__name__ == "Eq"
                ):
                    code += "{0} {1} {2} == {3};\n".format(
                        traverse(node.target, args, forflag, declared),
                        operator,
                        traverse(node.value.left, args, forflag, declared),
                        traverse(node.value.comparators[0], args, forflag, declared),
                    )
                else:
                    raise Exception(
                        "Unhandled Compare node {0}. Please inform the developers.".format(
                            node.value.ops[0]
                        )
                    )
            else:
                code = ""
                if flag and (
                    traverse(node.target, args, forflag, declared) not in declared
                ):
                    code += "auto "
                    declared.append(traverse(node.target, args, forflag, declared))
                code += "{0} {1} {2};\n".format(
                    traverse(node.target, args, forflag, declared),
                    operator,
                    traverse(node.value, args, forflag, declared),
                )
    else:
        raise Exception("Unhandled node {0}".format(node.__class__.__name__))
    return code


def getbody(pycode, args):
    code = ""
    tree = ast.parse(pycode).body[0]
    declared = []
    for node in tree.body:
        code += traverse(node, args, False, declared)
    return code


def getlenarg(pycode):
    tree = ast.parse(pycode).body[0]
    forargs = set()
    for node in tree.body:
        if node.__class__.__name__ == "For":
            forargs.add(traverse(node.iter.args[0]))
        elif node.__class__.__name__ == "While":
            assert node.test.__class__.__name__ == "Compare"
            assert len(node.test.ops) == 1
            assert node.test.ops[0].__class__.__name__ == "Lt"
            assert len(node.test.comparators) == 1
            forargs.add(traverse(node.test.comparators[0]))
    if len(forargs) == 0:
        return 1
    else:
        assert len(forargs) == 1
        return next(iter(forargs))


def getctype(typename):
    pointercount = 0
    if "Const[" in typename:
        typename = typename[:-1]
        typename = typename.replace("Const[", "", 1)
        cpptype = "const "
    else:
        cpptype = ""
    while "List[" in typename:
        typename = typename[5:]
        typename = typename[:-1]
        pointercount += 1
    cpptype += typename + "*" * pointercount
    return cpptype


def gettemplateargs(spec):
    templateargs = {}
    if "specializations" in spec.keys():
        typelist = []
        count = 0
        templascii = 65
        for childfunc in spec["specializations"]:
            for i in range(len(childfunc["args"])):
                if len(typelist) < i + 1:
                    typelist.append(list(childfunc["args"][i].values())[0])
                else:
                    if typelist[i] != list(childfunc["args"][i].values())[0]:
                        templateargs[list(childfunc["args"][i].keys())[0]] = chr(
                            templascii
                        )
                        count += 1
                        templascii += 1
    return templateargs


def getparentargs(templateargs, spec):
    args = OrderedDict()
    if "specializations" in spec.keys():
        for arg in spec["specializations"][0]["args"]:
            argname = list(arg.keys())[0]
            if list(arg.keys())[0] in templateargs.keys():
                if "*" in getctype(list(arg.values())[0]):
                    argname = "*" + argname
                if "Const[" in list(arg.values())[0]:
                    args[argname] = "const " + templateargs[list(arg.keys())[0]]
                else:
                    args[argname] = templateargs[list(arg.keys())[0]]
            else:
                args[argname] = getctype(list(arg.values())[0])
    else:
        for arg in spec["args"]:
            argname = list(arg.keys())[0]
            if argname in spec["outparams"]:
                argname = "*" + argname
            if "*" not in argname:
                args[argname] = list(arg.values())[0]
    return args


def getchildargs(childfunc, spec):
    args = OrderedDict()
    for arg in childfunc["args"]:
        for argname, typename in arg.items():
            args[argname] = getctype(typename)
    return args


def gettemplatestring(templateargs):
    count = 0
    templatestring = ""
    for x in templateargs.values():
        if count == 0:
            templatestring += "typename " + x
            count += 1
        else:
            templatestring += ", typename " + x
    return templatestring


def getdecl(name, args, templatestring, parent=False, solo=False):
    code = ""
    if templatestring != "":
        code += "template <" + templatestring + ">\n"
    if parent:
        code += "__global__\n"
    count = 0
    for key, value in args.items():
        if count == 0:
            params = value + " " + key
            count += 1
        else:
            params += ", " + value + " " + key
    if parent:
        code += (
            "void cuda" + name[len("awkward") :] + "(" + params + ", ERROR* err) {\n"
        )
    else:
        code += "ERROR " + name + "(" + params + ") {\n"
    return code


def gettemplatetypes(spec, templateargs):
    count = 0
    code = ""
    for arg in spec["args"]:
        for argname, typename in arg.items():
            if argname in templateargs.keys():
                if count == 0:
                    code += getctype(typename).replace("*", "")
                    count += 1
                else:
                    code += ", " + getctype(typename).replace("*", "")
    if "const " in code:
        code = code.replace("const ", "")
    return code


def getparamnames(args):
    count = 0
    for arg in args.keys():
        if count == 0:
            code = arg
            count += 1
        else:
            code += ", " + arg
    return code


def getcode(indspec):
    templateargs = gettemplateargs(indspec)
    args = getparentargs(templateargs, indspec)
    if "specializations" in indspec.keys():
        templatestring = gettemplatestring(templateargs)
    else:
        templatestring = ""
        args = getchildargs(indspec, indspec)
    code = getdecl(
        indspec["name"],
        args,
        templatestring,
        parent=True,
        solo="specializations" in indspec.keys(),
    )
    code += """  int64_t block_id = blockIdx.x + blockIdx.y * gridDim.x + gridDim.x * gridDim.y * blockIdx.z;
int64_t thread_id = block_id * blockDim.x + threadIdx.x;
"""
    code += getbody(indspec["definition"], args)
    code += "}\n\n"
    if "specializations" in indspec.keys():
        for childfunc in indspec["specializations"]:
            args = getchildargs(childfunc, indspec)
            code += getdecl(childfunc["name"], args, "")
            lenarg = getlenarg(indspec["definition"])
            code += """  dim3 blocks_per_grid;
dim3 threads_per_block;

if ({0} > 1024) {{
blocks_per_grid = dim3(ceil({0} / 1024.0), 1, 1);
threads_per_block = dim3(1024, 1, 1);
}} else {{
blocks_per_grid = dim3(1, 1, 1);
threads_per_block = dim3({0}, 1, 1);
}}
""".format(
                lenarg
            )
            code += " " * 2 + "ERROR h_err = success();\n"
            code += " " * 2 + "ERROR* err = &h_err;\n"
            code += " " * 2 + "ERROR* d_err;\n"
            code += " " * 2 + "cudaMalloc((void**)&d_err, sizeof(ERROR));\n"
            code += (
                " " * 2
                + "cudaMemcpy(d_err, err, sizeof(ERROR), cudaMemcpyHostToDevice);\n"
            )
            templatetypes = gettemplatetypes(childfunc, templateargs)
            paramnames = getparamnames(args)
            code += " " * 2 + "cuda" + indspec["name"][len("awkward") :]
            if templatetypes is not None and len(templatetypes) > 0:
                code += "<" + templatetypes + ">"
            code += (
                " <<<blocks_per_grid, threads_per_block>>>("
                + paramnames
                + ", d_err);\n"
            )
            code += " " * 2 + "cudaDeviceSynchronize();\n"
            code += (
                " " * 2
                + "cudaMemcpy(err, d_err, sizeof(ERROR), cudaMemcpyDeviceToHost);\n"
            )
            code += " " * 2 + "cudaFree(d_err);\n"
            code += " " * 2 + "return *err;\n"
            code += "}\n\n"
    else:
        code += getdecl(indspec["name"], args, "")
        lenarg = getlenarg(indspec["definition"])
        code += """  dim3 blocks_per_grid;
dim3 threads_per_block;

if ({0} > 1024) {{
blocks_per_grid = dim3(ceil({0} / 1024.0), 1, 1);
threads_per_block = dim3(1024, 1, 1);
}} else {{
blocks_per_grid = dim3(1, 1, 1);
threads_per_block = dim3({0}, 1, 1);
}}
""".format(
            lenarg
        )
        code += " " * 2 + "ERROR h_err = success();\n"
        code += " " * 2 + "ERROR* err = &h_err;\n"
        code += " " * 2 + "ERROR* d_err;\n"
        code += " " * 2 + "cudaMalloc((void**)&d_err, sizeof(ERROR));\n"
        code += (
            " " * 2 + "cudaMemcpy(d_err, err, sizeof(ERROR), cudaMemcpyHostToDevice);\n"
        )
        paramnames = getparamnames(args)
        code += (
            " " * 2
            + "cuda"
            + indspec["name"][len("awkward") :]
            + "<<<blocks_per_grid, threads_per_block>>>("
            + paramnames
            + ", d_err);\n"
        )
        code += " " * 2 + "cudaDeviceSynchronize();\n"
        code += (
            " " * 2 + "cudaMemcpy(d_err, err, sizeof(ERROR), cudaMemcpyDeviceToHost);\n"
        )
        code += " " * 2 + "cudaFree(d_err);\n"
        code += " " * 2 + "return *err;\n"
        code += "}\n\n"
    return code


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("kernelname", nargs="?")
    args = arg_parser.parse_args()
    kernelname = args.kernelname
    with open(
        os.path.join(CURRENT_DIR, "..", "kernel-specification", "kernelnames.yml")
    ) as infile:
        mainspec = yaml.safe_load(infile)["kernels"]
        code = """#include "awkward/kernels/operations.h"
#include "awkward/kernels/identities.h"
#include "awkward/kernels/getitem.h"
#include "awkward/kernels/reducers.h"
#include <cstdio>

"""
        for filedir in mainspec.values():
            for relpath in filedir.values():
                with open(
                    os.path.join(CURRENT_DIR, "..", "kernel-specification", relpath)
                ) as specfile:
                    indspec = yaml.safe_load(specfile)[0]
                    if indspec["name"] == kernelname and (
                        kernelname in KERNEL_WHITELIST or kernelname in KERNEL_CURIOUS
                    ):
                        code = getcode(indspec)
                        print(code)
                        break
                    if kernelname is None and indspec["name"] in KERNEL_WHITELIST:
                        with open(
                            os.path.join(
                                CURRENT_DIR,
                                "..",
                                "src",
                                "cuda-kernels",
                                indspec["name"] + ".cu",
                            ),
                            "w",
                        ) as outfile:
                            err_macro = '#define FILENAME(line) FILENAME_FOR_EXCEPTIONS_CUDA("src/cuda-kernels/{0}.cu", line)\n\n'.format(
                                indspec["name"]
                            )
                            outfile.write(err_macro + code + getcode(indspec))