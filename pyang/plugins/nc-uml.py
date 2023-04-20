"""NC UML extension plugin
"""
import optparse

from pyang import plugin
from pyang import error
from pyang import util
from pyang.plugins import uml

nc_uml_module_name = 'nc-uml'

class nc_uml_emitter(uml.uml_emitter):
    ctx_nc_extrefs = True
    ctx_nc_intrefs = True
    ctx_nc_leafref_color = ''
    ctx_nc_external_reference_color = ''
    ctx_nc_internal_reference_color = ''

    def __init__(self, ctx):
        super().__init__(ctx)
        self.i_modules = []
        self.e_modules = []
        no = ctx.opts.nc_uml_no.split(",")
        self.ctx_nc_extrefs = not "extref" in no
        self.ctx_nc_intrefs = not "intref" in no
        self.ctx_nc_leafref_color = ctx.opts.nc_uml_leafref_color
        self.ctx_nc_skinparams = {}
        self.ctx_nc_external_reference_color = ctx.opts.nc_uml_external_reference_color
        self.ctx_nc_internal_reference_color = ctx.opts.nc_uml_internal_reference_color
        self.ctx_nc_characteristic_color = ctx.opts.nc_uml_characteristic_color
        if ctx.opts.nc_uml_skinparams:
            self.ctx_nc_skinparams = dict(s.split(':', 1) for s in ctx.opts.nc_uml_skinparams.split(","))

    def emit_modules(self, modules, fd):
        for module in modules:
            if not self.ctx_no_module:
                self.emit_module_header(module, fd)
            self.emit_module_class(module, fd)
            for s in module.substmts:
                self.emit_stmt(module, s, fd)

            if not self.ctx_filterfile:
                self.post_process_module(fd)

    def emit_container(self, parent, node, fd):
        presence = node.search_one("presence")
        if presence is not None:
            cardinality = "0..1"
        else:
            cardinality = "1"

        if not self.ctx_filterfile:
        # and (not self.ctx_usefilterfile or self.full_path(node) in self.filterpaths):
            color = self.ctx_nc_characteristic_color if parent.keyword == 'module' else ''
            fd.write('class \"%s\" as  %s <<container>> %s\n' %(self.full_display_path(node), self.full_path(node), color))
            fd.write('%s *-- \"%s\" %s \n' %(self.full_path(parent), cardinality, self.full_path(node)))
        else:
            fd.write(self.full_path(node) + '\n')

    def emit_list(self, parent, node, fd):
        if not self.ctx_filterfile:
            color = self.ctx_nc_characteristic_color if parent.keyword == 'module' else ''
            fd.write('class \"%s\" as %s << (L, #FF7700) list>> %s\n' %(self.full_display_path(node), self.full_path(node), color))
            minelem = '0'
            maxelem = 'N'
            oby = ''
            mi = node.search_one('min-elements')
            if mi is not None:
                minelem = mi.arg
            ma = node.search_one('max-elements')
            if ma is not None:
                maxelem = ma.arg
            orderedby = node.search_one('ordered-by')
            if orderedby is not None:
                oby = ': ordered-by : ' + orderedby.arg
            fd.write('%s *-- \"%s..%s\" %s %s\n' %(self.full_path(parent), minelem, maxelem, self.full_path(node), oby))
        else:
            fd.write(self.full_path(node) + '\n')

    def post_process_diagram(self, fd):
        super().post_process_diagram(fd)
        if self.ctx_nc_extrefs:
            self.emit_modules(self.e_modules, fd)

    def emit_must_leaf(self, parent, node, fd):
        super().emit_must_leaf(parent, node, fd)
        self.emit_nc_reference(node, fd)

    def emit_nc_reference(self, node, fd):
        if not hasattr(node, 'i_nc_references'):
            return
        for r in node.i_nc_references:
            (_, i_leafref_ptr, _) = r
            (ptr, pos) = i_leafref_ptr
            color = None
            if node.i_module == ptr.i_module:
                if not self.ctx_nc_intrefs:
                    return
                color = self.ctx_nc_internal_reference_color
            else:
                if not self.ctx_nc_extrefs:
                    return
                if ptr.i_module not in self.i_modules and ptr.i_module not in self.e_modules:
                    self.e_modules.append(ptr.i_module)
                color = self.ctx_nc_external_reference_color
            self.leafrefs.append(self.full_path(node.parent) + '-' + color + '->' + '"' + ptr.arg + '"' + self.full_path(ptr.parent) + ': ' + node.arg + '\n')

    def emit_stmt(self, mod, stmt, fd):
        if stmt.keyword == 'uses':
            if not self.ctx_filterfile and not self._ctx.opts.uml_inline:
                fd.write('%s : %s {uses} \n' %(self.full_path(mod), stmt.arg))
            if not self._ctx.opts.uml_inline:
                self.emit_uses(mod, stmt)
            if hasattr(stmt, 'i_grouping') and (self._ctx.opts.uml_inline):
                grouping_node = stmt.i_grouping
                if grouping_node is not None:
                    # inline grouping here
                    # sys.stderr.write('Found  target grouping to inline %s %s \n' %(grouping_node.keyword, grouping_node.arg))
                    targets = [s.i_target_node for s in stmt.substmts if s.keyword == 'augment']
                    children = [ch for ch in mod.i_children if hasattr(ch, 'i_uses') and stmt in ch.i_uses]
                    for child in children:
                        child.parent = mod
                        self.emit_child_stmt(mod, child, fd, True, child in targets)
        else:
            super().emit_stmt(mod, stmt, fd)

    def emit_uml_header(self, title, fd):
        super().emit_uml_header(title, fd)
        for k in self.ctx_nc_skinparams:
            fd.write('skinparam %s %s\n' %(k, self.ctx_nc_skinparams[k]))

    def typestring(self, node):
        t = node.search_one('type')
        s = t.arg
        if t.arg == 'leafref':
            # sys.stderr.write('in leafref \n')
            s = s + ' : '
            p = t.search_one('path')
            if p is not None:
                # inthismodule, n = self.find_target_node(p)
                leafrefkey = p.arg
                leafrefkey =  leafrefkey[leafrefkey.rfind("/")+1:]
                leafrefparent = p.arg
                leafrefparent = leafrefparent[0:(leafrefparent.rfind("/"))]

                # shorten leafref attribute stuff here....
                if self.ctx_truncate_leafrefs:
                    s = s + '...' + leafrefkey
                else:
                    s = s + p.arg

                # leafrefs might contain functions like current and deref wich makes PlantUML turn it into
                # methods. Replace () with {}
                s = s.replace('(', '{')
                s = s.replace(')', '}')

                if node.i_leafref_ptr is not None:
                    n = node.i_leafref_ptr[0]
                else:
                    n = None

                prefix, _ = util.split_identifier(p.arg)
                # FIXME: previous code skipped first char, possibly in error
                prefix = self.thismod_prefix if prefix is None else prefix[1:]

                if n is not None:
                    if node.keyword == 'typedef':
                        self.leafrefs.append(self.make_plantuml_keyword(node.arg) + '-' + self.ctx_nc_leafref_color + '->' + '"' + leafrefkey + '"' + self.full_path(n.parent) + ': ' + node.arg + '\n')
                    else:
                        self.leafrefs.append(self.full_path(node.parent) + '-' + self.ctx_nc_leafref_color + '->' + '"' + leafrefkey + '"' + self.full_path(n.parent) + ': ' + node.arg + '\n')
                    if prefix not in self.module_prefixes:
                        self.post_strings.append('class \"%s\" as %s <<leafref>> \n' %(leafrefparent, self.full_path(n.parent)))
                        # self.post_strings.append('%s : %s\n' %(self.full_path(n.parent), leafrefkey))
                        sys.stderr.write("Info: Leafref %s outside diagram. Prefix = %s\n" %(p.arg, prefix))

                else:
                    sys.stderr.write("Info: Did not find leafref target %s\n" %p.arg)
        else:
            s = super().typestring(node)

        return s

class NCUMLPlugin(uml.UMLPlugin):
    def __init__(self):
        plugin.PyangPlugin.__init__(self, nc_uml_module_name)

    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--nc-uml-no",
                                 dest="nc_uml_no",
                                 default = "",
                                 help="Suppress parts of the diagram. \nValid suppress values are: extref, intref\nExample --nc-uml-no=extref,intref"),
            optparse.make_option("--nc-uml-leafref-color",
                                 dest="nc_uml_leafref_color",
                                 default = "",
                                 help="sets the color of leafref links\nExample --uml-leafref-color='[#red]'"),
            optparse.make_option("--nc-uml-skinparams",
                                 dest="nc_uml_skinparams",
                                 default = "",
                                 help="Adds general UML skinparams. The values \nExample --uml-skinparams=ArrowColor:blue,FileFontColor:red"),
            optparse.make_option("--nc-uml-external-reference-color",
                                 dest="nc_uml_external_reference_color",
                                 default = "",
                                 help="sets the color of external reference links\nExample --uml-external-reference-color='[#red]'"),
            optparse.make_option("--nc-uml-internal-reference-color",
                                 dest="nc_uml_internal_reference_color",
                                 default = "",
                                 help="sets the color of internal reference links\nExample --uml-internal-reference-color='[#red]'"),
            optparse.make_option("--nc-uml-characteristic-color",
                                 dest="nc_uml_characteristic_color",
                                 default = "",
                                 help="sets the color of internal reference links\nExample --uml-characteristic-color='#red'"),
            ]
        if hasattr(optparser, 'nc_uml_opts'):
            g = optparser.nc_uml_opts
        else:
            g = optparser.add_option_group("NC UML specific options")
            optparser.nc_uml_opts = g
        g.add_options(optlist)

    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts[nc_uml_module_name] = self

    def emit(self, ctx, modules, fd):
        for epos, etag, eargs in ctx.errors:
            if ((epos.top is None or epos.top.arg in self.mods) and
                error.is_error(error.err_level(etag))):
                self.fatal("%s contains errors" % epos.top.arg)


        if ctx.opts.uml_pages_layout is not None:
            if re.match('[0-9]x[0-9]', ctx.opts.uml_pages_layout) is None:
                self.fatal("Illegal page split option %s, should be [0-9]x[0-9], example 2x2" % ctx.opts.uml_pages_layout)


        umldoc = nc_uml_emitter(ctx)
        umldoc.emit(modules, fd)

def pyang_plugin_init():
    p = NCUMLPlugin()
    plugin.register_plugin(p)
