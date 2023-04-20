"""NC extension plugin
"""
import optparse

from pyang import plugin
from pyang import error
from pyang import statements
from pyang import grammar
from pyang.error import err_add

nc_module_name = 'nc-service-extensions'
nc_reference_arg = (nc_module_name, 'reference')

nc_error_codes = {
    'NC_MODULE_NOT_FOUND':
      (4,
       'module "%s" used within NC reference is not found, unable to verify paths (reported only once)'),
    'NC_MISMATCHED_TYPES':
      (2,
       'source type (%s) doesn\'t match destination type (%s)'),
    'NC_LEAFREF_RESTRICTION':
      (2,
       'leaf or leaf-list node of type \'leafref\' cannot use NC reference'),
    }

nc_stmts = [
    ('reference', '*',
     ('string', []),
     ['leaf', 'leaf-list']),
    ('displayed-name', '?',
     ('string', []),
     ['leaf', 'leaf-list', 'container', 'list']),
    ('version', '?',
     ('string', []),
     ['module']),
    ]

nc_references = {}
first_run = True

def validate_nc_reference(ctx, stmt):
    if not first_run:
        return
    if hasattr(stmt, 'i_is_validated'):
        # already validated
        return
    type_str = statements.get_type(stmt.parent)
    if type_str == 'leafref':
        err_add(ctx.errors, stmt.pos, 'NC_LEAFREF_RESTRICTION', ())
        return
    nc_references[stmt] = None
    stmt.i_is_validated = 'in_progress'

class NCPlugin(plugin.PyangPlugin):
    def __init__(self):
        plugin.PyangPlugin.__init__(self, 'nc')
        self.nc_service_ids = []
        self.nc_added_modules = []
        self.register()

    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--nc-service-attribute-name",
                                 action="store_true",
                                 dest="nc_service_attribute_name",
                                 default = "cfs-id",
                                 help="The name of service attribute, used to distinguish different instance of given service.\nDefault value: 'cfs-id'"),
            optparse.make_option("--nc-service-attribute-type",
                                 action="store_true",
                                 dest="nc_service_attribute_type",
                                 default = "tsisde2e:reference-cfs-id",
                                 help="The type of service attribute.\nDefault value: 'tsisde2e:reference-cfs-id'"),
            ]
        if hasattr(optparser, 'nc_opts'):
            g = optparser.nc_opts
        else:
            g = optparser.add_option_group('NC specific options')
            optparser.nc_opts = g
        g.add_options(optlist)

    def post_validate_ctx(self, ctx, modules):
        global first_run
        if not first_run:
            return
        first_run = False

        # create fake top level module
        top = self.new_statement(None, None, error.Position(nc_module_name), 'module', nc_module_name)
        top.i_orig_module = top
        top.i_module = top
        self.new_statement(top, top, top.pos, 'yang-version', '1.1')
        self.new_statement(top, top, top.pos, 'namespace', 'http://netcracker.com/yang/' + nc_module_name)
        self.new_statement(top, top, top.pos, 'prefix', nc_module_name)
        statements.v_init_module(ctx, top)
        statements.v_grammar_module(ctx, top)

        # create fake service-id reference in real modules
        for m in modules:
            top.i_prefixes = top.i_prefixes | m.i_prefixes
            self.create_service_id(ctx, m)

        # create fake leafrefs in real modules
        errors_to_remove = []
        i = len(ctx.errors)
        for stmt in nc_references:
            leaf_stmt = self.create_leafref(top, stmt)
            self.check_leafref(ctx, stmt, leaf_stmt)

        # check errors which we can handle
        recheck = False
        count = len(ctx.errors)
        while i < count:
            p, t, a = ctx.errors[i]
            if t == 'PREFIX_NOT_DEFINED':
                errors_to_remove.insert(0, i)
                top.i_missing_prefixes.pop(a)
                m = ctx.search_module(top.pos, a)
                if m is not None:
                    statements.validate_module(ctx, m)
                    self.create_service_id(ctx, m)
                    top.i_prefixes[a] = (a, None)
                    recheck = True
                    self.nc_added_modules.append(m)
                else:
                    err_add(ctx.errors, p, 'NC_MODULE_NOT_FOUND', a)
            elif t == 'LEAFREF_DEREF_NOT_LEAFREF':
                (arg, pos) = a
                for s in nc_references:
                    if s.parent.pos == pos and s.parent.arg == arg:
                        errors_to_remove.insert(0, i)
            i += 1

        # re-check after adding missing modules
        if recheck:
            for stmt in nc_references:
                leaf_stmt = nc_references[stmt]
                self.check_leafref(ctx, stmt, leaf_stmt)

        # remove top level errors of fake module
        count = len(ctx.errors)
        while i < count:
            p, t, a = ctx.errors[i]
            if p.line == top.pos.line and p.ref == top.pos.ref and p.top == top.pos.top:
                errors_to_remove.insert(0, i)
            i += 1

        # remove all invalid errors
        for i in errors_to_remove:
            ctx.errors.pop(i)

        # final clean-up to allow proper output of other plugins
        for s in self.nc_service_ids:
            self.remove_statement(s.parent, s)
        for s in nc_references.copy():
            leaf_stmt = nc_references.pop(s)
            self.remove_statement(leaf_stmt.parent, leaf_stmt)

        self.remove_not_used(None, self.nc_added_modules)

    def register(self):
        # Register that we handle extensions from the YANG module 'nc-service-extensions'
        grammar.register_extension_module(nc_module_name)
        for (stmt, occurance, (arg, rules), add_to_stmts) in nc_stmts:
            grammar.add_stmt((nc_module_name, stmt), (arg, rules))
            grammar.add_to_stmts_rules(add_to_stmts,
                                   [((nc_module_name, stmt), occurance)])

        # Register the error-codes
        for tag in nc_error_codes:
            level, fmt = nc_error_codes[tag]
            error.add_error_code(tag, level, fmt)

        # Register the statements
        statements.add_data_keyword(nc_reference_arg)
        statements.add_keyword_with_children(nc_reference_arg)
        statements.add_keyword_phase_i_children('reference_2', nc_reference_arg)
        statements.add_keywords_with_no_explicit_config(nc_reference_arg)
        statements.add_validation_fun('reference_2', [nc_reference_arg], lambda ctx, s:validate_nc_reference(ctx, s))

    def set_i_module(self, leaf_stmt):
        type_stmt = leaf_stmt.substmts[0]
        path_stmt = type_stmt.substmts[0]
        for s in [leaf_stmt, type_stmt, path_stmt]:
            s.i_orig_module = s.top
            s.i_module = s.top

    def new_statement(self, top, parent, pos, keyword, arg):
        stmt = statements.new_statement(top, parent, pos, keyword, arg)
        stmt.i_orig_module = top
        stmt.i_module = top
        if parent:
            parent.substmts.append(stmt)
            if hasattr(parent, 'i_children'):
                parent.i_children.append(stmt)
        return stmt

    def remove_statement(self, parent, stmt):
        if not parent:
            return
        if stmt in parent.substmts:
            parent.substmts.remove(stmt)
        if hasattr(parent, 'i_children'):
            if stmt in parent.i_children:
                parent.i_children.remove(stmt)

    def init_leafref(self, ctx, leaf_stmt):
        type_stmt = leaf_stmt.substmts[0]
        path_stmt = type_stmt.substmts[0]
        statements.v_init_stmt(ctx, leaf_stmt)
        statements.v_init_stmt(ctx, type_stmt)
        statements.v_init_stmt(ctx, path_stmt)
        if not grammar.chk_statement(ctx, leaf_stmt, grammar.data_def_stmts):
            return;
        statements.v_grammar_all(ctx, leaf_stmt)
        statements.v_grammar_all(ctx, type_stmt)
        statements.v_grammar_all(ctx, path_stmt)
        statements.v_type_type(ctx, type_stmt)
        statements.v_type_leaf(ctx, leaf_stmt)
        statements.v_reference_leaf_leafref(ctx, leaf_stmt)
        statements.v_inherit_properties(ctx, leaf_stmt.parent)

    def create_leafref(self, top, stmt):
        i = 0
        for ch in stmt.parent.parent.i_children:
            if ch.arg.startswith(stmt.parent.arg + '-' + nc_module_name):
                i += 1
        leaf_stmt = self.new_statement(stmt.i_module, stmt.parent.parent, stmt.pos, 'leaf', stmt.parent.arg + '-' + nc_module_name + '-' + str(i))
        type_stmt = self.new_statement(stmt.i_module, leaf_stmt, stmt.pos, 'type', 'leafref')
        path_stmt = self.new_statement(top, type_stmt, stmt.pos, 'path', stmt.arg)
        nc_references[stmt] = leaf_stmt
        return leaf_stmt

    def get_final_qualified_type(self, stmt, follow):
        if follow and hasattr(stmt, 'i_leafref_ptr') and stmt.i_leafref_ptr:
            (ptr, pos) = stmt.i_leafref_ptr
            return statements.get_qualified_type(ptr)
        else:
            return statements.get_qualified_type(stmt)

    def check_leafref(self, ctx, orig, fake):
        fake.internal_reset()
        self.set_i_module(fake)
        self.init_leafref(ctx, fake)
        orig.parent.i_leafref = fake.i_leafref
        orig.parent.i_leafref_ptr = fake.i_leafref_ptr
        orig.parent.i_leafref_expanded = fake.i_leafref_expanded
        if hasattr(orig, 'i_nc_references'):
            orig.parent.i_nc_references.append((fake.i_leafref, fake.i_leafref_ptr, fake.i_leafref_expanded))
        else:
            orig.parent.i_nc_references = [(fake.i_leafref, fake.i_leafref_ptr, fake.i_leafref_expanded)]
        if hasattr(fake, 'i_derefed_leaf'):
            orig.parent.i_derefed_leaf = fake.i_derefed_leaf
        if fake.i_leafref_ptr:
            source_type = self.get_final_qualified_type(orig.parent, False)
            (ptr, pos) = fake.i_leafref_ptr
            destination_type = self.get_final_qualified_type(ptr, True)
            if source_type != destination_type:
                err_add(ctx.errors, orig.parent.pos, 'NC_MISMATCHED_TYPES', (source_type, destination_type))
            self.mark_as_used(ptr)

    def create_service_id(self, ctx, module):
        leaf_stmt = self.new_statement(module, module, module.pos, 'leaf', ctx.opts.nc_service_attribute_name)
        type_stmt = self.new_statement(module, leaf_stmt, module.pos, 'type', ctx.opts.nc_service_attribute_type)
        mandatory_stmt = self.new_statement(module, leaf_stmt, module.pos, 'mandatory', 'true')
        statements.v_init_stmt(ctx, leaf_stmt)
        statements.v_init_stmt(ctx, type_stmt)
        statements.v_init_stmt(ctx, mandatory_stmt)
        if not grammar.chk_statement(ctx, leaf_stmt, grammar.data_def_stmts):
            return;
        statements.v_grammar_all(ctx, leaf_stmt)
        statements.v_grammar_all(ctx, type_stmt)
        statements.v_grammar_all(ctx, mandatory_stmt)
        statements.v_type_type(ctx, type_stmt)
        statements.v_inherit_properties(ctx, module)
        self.nc_service_ids.append(leaf_stmt)

    def mark_as_used(self, s):
        if not hasattr(s, 'i_nc_used'):
            s.i_nc_used = True
            if s.parent and s.parent != s and not hasattr(s.parent, 'i_nc_used'):
                self.mark_as_used(s.parent)

    def remove_not_used(self, parent, stmts):
        for s in stmts.copy():
            if hasattr(s, 'i_nc_used'):
                self.remove_not_used(s, s.substmts)
                if hasattr(s, 'i_children'):
                    self.remove_not_used(s, s.i_children)
            elif s.keyword in statements.data_keywords:
                self.remove_statement(parent, s)

def pyang_plugin_init():
    p = NCPlugin()
    plugin.register_plugin(p)
