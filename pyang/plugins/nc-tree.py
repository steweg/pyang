"""NC tree extension plugin
"""
from pyang import plugin
from pyang import util
from pyang.plugins import nc
from pyang.plugins import tree

nc_tree_module_name = 'nc-tree'

def nc_get_reference_path(s, prefix_with_modname):
    paths = s.search(nc.nc_reference_arg)
    targets = []
    for p in paths:
        targets.append(nc_compact_path(s, p, prefix_with_modname))
    if len(targets) > 0:
        return "(-> %s)" % " | ".join(targets)
    else:
        return ""

def nc_compact_path(s, p, prefix_with_modname):
    # Try to make the path as compact as possible.
    # Remove local prefixes, and only use prefix when
    # there is a module change in the path.
    target = []
    curprefix = s.i_module.i_prefix
    for name in p.arg.split('/'):
        prefix, name = util.split_identifier(name)
        if prefix is None or prefix == curprefix:
            target.append(name)
        else:
            if prefix_with_modname:
                if prefix in s.i_module.i_prefixes:
                    # Try to map the prefix to the module name
                    module_name, _ = s.i_module.i_prefixes[prefix]
                else:
                    # If we can't then fall back to the prefix
                    module_name = prefix
                target.append(module_name + ':' + name)
            else:
                target.append(prefix + ':' + name)
            curprefix = prefix
    return "/".join(target)

def nc_get_typename(s, prefix_with_modname=False):
    t = s.search_one('type')
    if t is not None:
        if t.arg == 'leafref':
            p = t.search_one('path')
            if p is not None:
                return "-> %s" % nc_compact_path(s, p, prefix_with_modname)
            else:
                # This should never be reached. Path MUST be present for
                # leafref type. See RFC6020 section 9.9.2
                # (https://tools.ietf.org/html/rfc6020#section-9.9.2)
                if prefix_with_modname:
                    prefix, name = util.split_identifier(t.arg)
                    if prefix is None:
                        # No prefix specified. Leave as is
                        return t.arg
                    else:
                        # Prefix found. Replace it with the module name
                        if prefix in s.i_module.i_prefixes:
                            # Try to map the prefix to the module name
                            module_name, _ = s.i_module.i_prefixes[prefix]
                        else:
                            # If we can't then fall back to the prefix
                            module_name = prefix
                        return module_name + ':' + name
                else:
                    return t.arg
        else:
            nc_reference = nc_get_reference_path(s, prefix_with_modname)
            if prefix_with_modname:
                prefix, name = util.split_identifier(t.arg)
                if prefix is None:
                    # No prefix specified. Leave as is
                    return " ".join([t.arg, nc_reference])
                else:
                    # Prefix found. Replace it with the module name
                    if prefix in s.i_module.i_prefixes:
                        # Try to map the prefix to the module name
                        module_name, _ = s.i_module.i_prefixes[prefix]
                    else:
                        # If we can't then fall back to the prefix
                        module_name = prefix
                    return " ".join([module_name + ':' + t.arg, nc_reference])
            else:
                return " ".join([t.arg, nc_reference])
    elif s.keyword == 'anydata':
        return '<anydata>'
    elif s.keyword == 'anyxml':
        return '<anyxml>'
    else:
        return ''

class NCTreePlugin(tree.TreePlugin):
    def __init__(self):
        plugin.PyangPlugin.__init__(self, nc_tree_module_name)
        # override static methods
        tree.get_typename = nc_get_typename

    def add_opts(self, optparser):
        pass

    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts[nc_tree_module_name] = self

def pyang_plugin_init():
    p = NCTreePlugin()
    plugin.register_plugin(p)
