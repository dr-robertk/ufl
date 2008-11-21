"""This module defines expression transformation utilities,
either converting UFL expressions to new UFL expressions or
converting UFL expressions to other representations."""

__authors__ = "Martin Sandve Alnes"
__date__ = "2008-05-07 -- 2008-11-21"

from itertools import izip, chain
from ufl.output import ufl_assert, ufl_error, ufl_warning
from ufl.common import camel2underscore, domain2dim
from ufl.base import Expr, Terminal
from ufl.indexing import Index, indices, complete_shape
from ufl.tensors import as_tensor, as_matrix, as_vector
from ufl.variable import Variable
from ufl.form import Form
from ufl.integral import Integral
from ufl.classes import all_ufl_classes
from ufl.algorithms.analysis import extract_duplications

# TODO: Remove these in time
def transform(expression, handlers):
    """Convert a UFLExpression according to rules defined by
    the mapping handlers = dict: class -> conversion function."""
    if isinstance(expression, Terminal):
        ops = ()
    else:
        ops = [transform(o, handlers) for o in expression.operands()]
    c = expression._uflid
    h = handlers.get(c, None)
    if c is None:
        ufl_error("Didn't find class %s among handlers." % c)
    return h(expression, *ops)


def transform_integrands(form, transformer):
    if isinstance(form, Form):
        newintegrals = []
        for integral in form.integrals():
            newintegrand = transformer(integral.integrand())
            newintegral= Integral(integral.domain_type(), integral.domain_id(), newintegrand)
            newintegrals.append(newintegral)
        newform = Form(newintegrals)
        return newform


class Transformer(object):
    """Base class for a visitor-like algorithm design pattern used to 
    transform expression trees from one representation to another."""
    def __init__(self, variable_cache=None):
        self._variable_cache = {} if variable_cache is None else variable_cache
        self._handlers = {}
        
        # For all UFL classes
        for uc in all_ufl_classes:
            # Iterate over the inheritance chain (assumes that all UFL classes has an Expr subclass as the first superclass)
            for c in uc.mro():
                # Register class uc with handler for the first encountered superclass
                fname = camel2underscore(c.__name__)
                if hasattr(self, fname):
                    self.register(uc, getattr(self, fname))
                    break
    
    def register(self, classobject, function):
        self._handlers[classobject] = function
    
    def visit(self, o):
        # Get handler for the UFL class of o (type(o) may be an external subclass of the actual UFL class)
        h = self._handlers.get(o._uflid)
        if h:
            # Did we find a handler that expects transformed children as input?
            if len(h.func_code.co_varnames) > 2:
                return h(o, *[self.visit(oo) for oo in o.operands()])
            # No, this is a handler that handles its own children (arguments self and o, where self is already bound).
            return h(o)
        # Failed to find a handler!
        raise RuntimeError("Can't handle objects of type %s" % str(type(o)))
    
    def reuse_if_possible(self, o, *operands):
        # Reuse o if possible, otherwise recreate
        return o if operands == o.operands() else type(o)(*operands)
    expr = reuse_if_possible
    
    def reuse(self, o):
        # Always reuse
        return o
    terminal = reuse
    
    def variable(self, o):
        # Check variable cache to reuse previously transformed variable if possible
        c = o._count
        v = self._variable_cache.get(c)
        if v is None:
            # Visit the expression our variable represents
            e = o._expression
            e2 = self.visit(o._expression)
            # Recreate Variable with same count if necessary
            if e is e2:
                return o
            v = Variable(e2, c)
            self._variable_cache[c] = v
        return v


class Replacer(Transformer):
    def __init__(self, mapping):
        Transformer.__init__(self)
        self._mapping = mapping
        ufl_assert(all(isinstance(k, Terminal) for k in mapping.keys()), \
                "Can only replace Terminal objects.")
    
    def terminal(self, o):
        e = self._mapping.get(o)
        return o if e is None else e


class TreeFlattener(Transformer):
    def __init__(self):
        Transformer.__init__(self)
    
    def sum_or_product(self, o, *ops):
        # FIXME: This is error prone for indexed products, consider: (u[i]*u[i])*(v[i]*v[i])
        c = type(o)
        operands = []
        for b in ops:
            if isinstance(b, c):
                operands.extend(b.operands())
            else:
                operands.append(b)
        return c(*operands)
    sum = sum_or_product
    product = sum_or_product

class Copier(Transformer):
    def __init__(self, mapping):
        Transformer.__init__(self)
    
    def expr(self, o, *ops):
        return type(o)(*ops)
    
    def variable(self, o):
        v = self._variable_cache.get(o._count)
        if v is None:
            e = self.visit(o._expression)
            v = Variable(e, o._count)
            self._variable_cache[o._count] = v
        return v


class VariableStripper(Transformer):
    def __init__(self, mapping):
        Transformer.__init__(self)
    
    def variable(self, o):
        return self.visit(o._expression)


#class OperatorApplier(Transformer):
#    "Implements mappings that can be defined through Python operators."
#    def __init__(self):
#        Transformer.__init__(self)
#    
#    def abs(self, o, a):
#        return abs(a)
#    
#    def sum(self, o, *ops):
#        return sum(ops)
#    
#    def division(self, o, a, b):
#        return a / b
#    
#    def power(self, o, a, b):
#        return a ** b
#    
#    def product(self, o, *ops):
#        return product(ops)
#    
#    def indexed(self, o, a, b):
#        return a[*b] if isinstance(b, tuple) else a[b]


# TODO: Indices will often mess up extract_duplications / mark_duplications.
# Can we renumber indices consistently from the leaves to avoid that problem?
# This may introduce many ComponentTensor/Indexed objects for relabeling of indices though.
# We probably need some kind of pattern matching to make this effective.
# That's another step towards a complete symbolic library...
# 
# What this does do well is insert Variables around subexpressions that the
# user actually identified manually in his code like in "a = ...; b = a*(1+a)",
# and expressions without indices (prior to expand_compounds).
class DuplicationMarker(Transformer):
    def __init__(self, duplications):
        Transformer.__init__(self)
        self._duplications = duplications
        self._variables = {}
    
    def expr(self, o, *ops):
        v = self._variables.get(o)
        if v is None:
            oo = o
            # reconstruct if necessary
            if not ops == o.operands():
                o = type(o)(*ops)
            if (oo in self._duplications) or (o in self._duplications):
                v = Variable(o)
                self._variables[o] = v
                self._variables[oo] = v
            else:
                v = o
        return v
    
    def terminal(self, o):
        return o
    
    def variable(self, o):
        e = o._expression
        v = self._variables.get(e)
        if v is None:
            e2 = self.visit(e)
            # Unwrap expression from the newly created Variable wrapper
            # unless the original expression was a Variable, in which
            # case we possibly need to keep the count for correctness.
            if (not isinstance(e, Variable)) and isinstance(e2, Variable):
                e2 = e2._expression
            v = self._variables.get(e2)
            if v is None:
                v = Variable(e2, o._count)
                self._variables[e] = v
                self._variables[e2] = v
        return v


# Note:
# To avoid typing errors, the expressions for cofactor and deviatoric parts 
# below were created with the script tensoralgebrastrings.py under ufl/scripts/
class CompoundExpander(Transformer):
    "Expands compound expressions to equivalent representations using basic operators."
    def __init__(self, geometric_dimension):
        Transformer.__init__(self)
        self._dim = geometric_dimension
    
    # ------------ Compound tensor operators
    
    def trace(self, o, A):
        i = Index()
        return A[i,i]
    
    def transposed(self, o, A):
        i, j = indices(2)
        return as_tensor(A[i, j], (j, i))
    
    def deviatoric(self, o, A):
        sh = complete_shape(A.shape(), self._dim)
        if sh[0] == 2:
            return as_matrix([[-A[1,1],A[0,1]],[A[1,0],-A[0,0]]])
        elif sh[0] == 3:
            return as_matrix([[-A[1,1]-A[2,2],A[0,1],A[0,2]],[A[1,0],-A[0,0]-A[2,2],A[1,2]],[A[2,0],A[2,1],-A[0,0]-A[1,1]]])
        ufl_error("dev(A) not implemented for dimension %s." % sh[0])
    
    def skew(self, o, A):
        i, j = indices(2)
        return as_matrix( (A[i,j] - A[j,i]) / 2, (i,j) )
    
    def cross(self, o, a, b):
        def c(i, j):
            return a[i]*b[j]-a[j]*b[i]
        return as_vector((c(1,2), c(2,0), c(0,1)))
    
    def dot(self, o, a, b):
        i = Index()
        aa = a[i] if (a.rank() == 1) else a[...,i]
        bb = b[i] if (b.rank() == 1) else b[i,...]
        return aa*bb
    
    def inner(self, o, a, b):
        ufl_assert(a.rank() == b.rank())
        ii = indices(a.rank())
        return a[ii]*b[ii]
    
    def outer(self, o, a, b):
        ii = indices(a.rank())
        jj = indices(b.rank())
        return a[ii]*b[jj]
    
    def determinant(self, o, A):
        sh = complete_shape(A.shape(), self._dim)
        if len(sh) == 0:
            return A
        ufl_assert(sh[0] == sh[1], "Expecting square matrix.")
        def det2D(B, i, j, k, l):
            return B[i,k]*B[j,l]-B[i,l]*B[j,k]
        if sh[0] == 2:
            return det2D(A, 0, 1, 0, 1)
        if sh[0] == 3:
            # TODO: Verify this expression
            return A[0,0]*det2D(A, 1, 2, 1, 2) + \
                   A[0,1]*det2D(A, 1, 2, 2, 0) + \
                   A[0,2]*det2D(A, 1, 2, 0, 1)
        # TODO: Implement generally for all dimensions?
        ufl_error("Determinant not implemented for dimension %d." % self._dim)
    
    def cofactor(self, o, A):
        sh = complete_shape(A.shape(), self._dim)
        ufl_assert(sh[0] == sh[1], "Expecting square matrix.")
        if sh[0] == 2:
            return as_matrix([[A[1,1], -A[0,1]], [-A[1,0], A[0,0]]])
        elif sh[0] == 3:
            return as_matrix([ \
                [ A[2,2]*A[1,1] - A[1,2]*A[2,1],
                 -A[0,1]*A[2,2] + A[0,2]*A[2,1],
                  A[0,1]*A[1,2] - A[0,2]*A[1,1]],
                [-A[2,2]*A[1,0] + A[1,2]*A[2,0],
                 -A[0,2]*A[2,0] + A[2,2]*A[0,0],
                  A[0,2]*A[1,0] - A[1,2]*A[0,0]],
                [ A[1,0]*A[2,1] - A[2,0]*A[1,1],
                  A[0,1]*A[2,0] - A[0,0]*A[2,1],
                  A[0,0]*A[1,1] - A[0,1]*A[1,0]] \
                ])
        elif sh[0] == 4:
            # TODO: Find common subexpressions here.
            # TODO: Better implementation?
            return as_matrix([ \
                [-A[3,3]*A[2,1]*A[1,2] + A[1,2]*A[3,1]*A[2,3] + A[1,1]*A[3,3]*A[2,2] - A[3,1]*A[2,2]*A[1,3] + A[2,1]*A[1,3]*A[3,2] - A[1,1]*A[3,2]*A[2,3],
                 -A[3,1]*A[0,2]*A[2,3] + A[0,1]*A[3,2]*A[2,3] - A[0,3]*A[2,1]*A[3,2] + A[3,3]*A[2,1]*A[0,2] - A[3,3]*A[0,1]*A[2,2] + A[0,3]*A[3,1]*A[2,2],
                  A[3,1]*A[1,3]*A[0,2] + A[1,1]*A[0,3]*A[3,2] - A[0,3]*A[1,2]*A[3,1] - A[0,1]*A[1,3]*A[3,2] + A[3,3]*A[1,2]*A[0,1] - A[1,1]*A[3,3]*A[0,2],
                  A[1,1]*A[0,2]*A[2,3] - A[2,1]*A[1,3]*A[0,2] + A[0,3]*A[2,1]*A[1,2] - A[1,2]*A[0,1]*A[2,3] - A[1,1]*A[0,3]*A[2,2] + A[0,1]*A[2,2]*A[1,3]],
                [ A[3,3]*A[1,2]*A[2,0] - A[3,0]*A[1,2]*A[2,3] + A[1,0]*A[3,2]*A[2,3] - A[3,3]*A[1,0]*A[2,2] - A[1,3]*A[3,2]*A[2,0] + A[3,0]*A[2,2]*A[1,3],
                  A[0,3]*A[3,2]*A[2,0] - A[0,3]*A[3,0]*A[2,2] + A[3,3]*A[0,0]*A[2,2] + A[3,0]*A[0,2]*A[2,3] - A[0,0]*A[3,2]*A[2,3] - A[3,3]*A[0,2]*A[2,0],
                 -A[3,3]*A[0,0]*A[1,2] + A[0,0]*A[1,3]*A[3,2] - A[3,0]*A[1,3]*A[0,2] + A[3,3]*A[1,0]*A[0,2] + A[0,3]*A[3,0]*A[1,2] - A[0,3]*A[1,0]*A[3,2],
                  A[0,3]*A[1,0]*A[2,2] + A[1,3]*A[0,2]*A[2,0] - A[0,0]*A[2,2]*A[1,3] - A[0,3]*A[1,2]*A[2,0] + A[0,0]*A[1,2]*A[2,3] - A[1,0]*A[0,2]*A[2,3]],
                [ A[3,1]*A[1,3]*A[2,0] + A[3,3]*A[2,1]*A[1,0] + A[1,1]*A[3,0]*A[2,3] - A[1,0]*A[3,1]*A[2,3] - A[3,0]*A[2,1]*A[1,3] - A[1,1]*A[3,3]*A[2,0],
                  A[3,3]*A[0,1]*A[2,0] - A[3,3]*A[0,0]*A[2,1] - A[0,3]*A[3,1]*A[2,0] - A[3,0]*A[0,1]*A[2,3] + A[0,0]*A[3,1]*A[2,3] + A[0,3]*A[3,0]*A[2,1],
                 -A[0,0]*A[3,1]*A[1,3] + A[0,3]*A[1,0]*A[3,1] - A[3,3]*A[1,0]*A[0,1] + A[1,1]*A[3,3]*A[0,0] - A[1,1]*A[0,3]*A[3,0] + A[3,0]*A[0,1]*A[1,3],
                  A[0,0]*A[2,1]*A[1,3] + A[1,0]*A[0,1]*A[2,3] - A[0,3]*A[2,1]*A[1,0] + A[1,1]*A[0,3]*A[2,0] - A[1,1]*A[0,0]*A[2,3] - A[0,1]*A[1,3]*A[2,0]],
                [-A[1,2]*A[3,1]*A[2,0] - A[2,1]*A[1,0]*A[3,2] + A[3,0]*A[2,1]*A[1,2] - A[1,1]*A[3,0]*A[2,2] + A[1,0]*A[3,1]*A[2,2] + A[1,1]*A[3,2]*A[2,0],
                 -A[3,0]*A[2,1]*A[0,2] - A[0,1]*A[3,2]*A[2,0] + A[3,1]*A[0,2]*A[2,0] - A[0,0]*A[3,1]*A[2,2] + A[3,0]*A[0,1]*A[2,2] + A[0,0]*A[2,1]*A[3,2],
                  A[0,0]*A[1,2]*A[3,1] - A[1,0]*A[3,1]*A[0,2] + A[1,1]*A[3,0]*A[0,2] + A[1,0]*A[0,1]*A[3,2] - A[3,0]*A[1,2]*A[0,1] - A[1,1]*A[0,0]*A[3,2],
                 -A[1,1]*A[0,2]*A[2,0] + A[2,1]*A[1,0]*A[0,2] + A[1,2]*A[0,1]*A[2,0] + A[1,1]*A[0,0]*A[2,2] - A[1,0]*A[0,1]*A[2,2] - A[0,0]*A[2,1]*A[1,2]] \
                ])
        ufl_error("Cofactor not implemented for dimension %s." % sh[0])
    
    def inverse(self, o, A):
        if A.rank() == 0:
            return 1.0 / A
        return self.cofactor(None, A) / self.determinant(None, A)  # TODO: Verify this expression. Ainv = Acofac / detA
    
    # ------------ Compound differential operators
    
    def div(self, o, a):
        i = Index()
        g = a[i] if a.rank() == 1 else a[...,i]
        return g.dx(i)
    
    def grad(self, o, a):
        ii = Index()
        if a.rank() > 0:
            jj = tuple(indices(a.rank()))
            return as_tensor(a[jj].dx(ii), tuple((ii,)+jj))
        return as_tensor(a.dx(ii), (ii,))
    
    def curl(self, o, a):
        raise NotImplementedError # TODO
    
    def rot(self, o, a):
        raise NotImplementedError # TODO


# ------------ User interface functions

def apply_transformer(e, transformer):
    if isinstance(e, Form):
        newintegrals = []
        for itg in e.integrals():
            newintegrand = transformer.visit(itg.integrand())
            newitg = Integral(itg.domain_type(), itg.domain_id(), newintegrand)
            newintegrals.append(newitg)
        return Form(newintegrals)
    ufl_assert(isinstance(e, Expr), "Expecting Form or Expr.")
    return transformer.visit(e)

def ufl2ufl(e):
    """Convert an UFL expression to a new UFL expression, with no changes.
    This is used for testing that objects in the expression behave as expected."""
    return apply_transformer(e, Transformer())

def ufl2uflcopy(e):
    """Convert an UFL expression to a new UFL expression.
    All nonterminal object instances are replaced with identical
    copies, while terminal objects are kept. This is used for
    testing that objects in the expression behave as expected."""
    return apply_transformer(e, Copier())

def replace(e, mapping):
    """Replace terminal objects in expression.
    
    @param e:
        An Expr or Form.
    @param mapping:
        A dict with from:to replacements to perform.
    """
    return apply_transformer(e, Replacer(mapping))

def flatten(e):
    """Convert an UFL expression to a new UFL expression, with sums 
    and products flattened from binary tree nodes to n-ary tree nodes."""
    ufl_warning("flatten doesn't work correctly for some indexed products, like (u[i]*v[i])*(q[i]*r[i])")
    return apply_transformer(e, TreeFlattener())

def expand_compounds(e, dim=None):
    """Expand compound objects into basic operators.
    Requires e to have a well defined domain, 
    for the geometric dimension to be defined."""
    if dim is None: dim = domain2dim[e.domain()]
    return apply_transformer(e, CompoundExpander(dim))

def strip_variables(e):
    return apply_transformer(e, VariableStripper())

def mark_duplications(e):
    """Wrap subexpressions that are equal (completely equal, not mathematically
    equivalent) in Variable objects to facilitate subexpression reuse."""
    duplications = extract_duplications(e)
    return apply_transformer(e, DuplicationMarker(duplications))

