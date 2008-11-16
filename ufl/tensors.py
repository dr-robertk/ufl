"""Classes used to group scalar expressions into expressions with rank > 0."""


__authors__ = "Martin Sandve Alnes"
__date__ = "2008-03-31 -- 2008-11-06"

from ufl.output import ufl_assert, ufl_warning
from ufl.base import Expr
from ufl.scalar import as_ufl
from ufl.indexing import Index, MultiIndex

# --- Classes representing tensors of UFL expressions ---

class ListTensor(Expr):
    __slots__ = ("_expressions", "_free_indices", "_shape")
    
    def __init__(self, *expressions):
        if isinstance(expressions[0], (list, tuple)):
            expressions = [ListTensor(*sub) for sub in expressions]
        
        if not all(isinstance(e, ListTensor) for e in expressions):
            expressions = [as_ufl(e) for e in expressions]
            ufl_assert(all(isinstance(e, Expr) for e in expressions), \
                "Expecting list of subtensors or expressions.")
        
        self._expressions = tuple(expressions)
        r = len(expressions)
        e = expressions[0]
        c = e.shape()
        self._shape = (r,) + c
        
        ufl_assert(all(sub.shape() == c for sub in expressions),
            "Inconsistent subtensor size.")
        
        indexset = set(e.free_indices())
        ufl_assert(all(not (indexset ^ set(sub.free_indices())) for sub in expressions), \
            "Can't combine subtensor expressions with different sets of free indices.") # TODO: Does this make sense?
    
    def operands(self):
        return self._expressions
    
    def free_indices(self):
        return self._expressions[0].free_indices()
    
    def index_dimensions(self):
        return self._expressions[0].index_dimensions()
    
    def shape(self):
        return self._shape
    
    def __str__(self):
        def substring(expressions, indent):
            ind = " "*indent
            if isinstance(expressions[0], ListTensor):
                s = (ind+",\n").join(substring(e._expressions, indent+2) for e in expressions)
                return ind + "[" + "\n" + s + "\n" + ind + "]"
            else:
                return ind + "[ %s ]" % ", ".join(repr(e) for e in expressions)
        sub = substring(self._expressions, 0)
        return "ListTensor(%s)" % sub
    
    def __repr__(self):
        return "ListTensor(%s)" % ", ".join(repr(e) for e in self._expressions)

class ComponentTensor(Expr):
    __slots__ = ("_expression", "_indices", "_free_indices", "_index_dimensions", "_shape")
    
    def __init__(self, expression, indices):
        ufl_assert(isinstance(expression, Expr), "Expecting ufl expression.")
        ufl_assert(expression.shape() == (), "Expecting scalar valued expression.")
        self._expression = expression
        
        if isinstance(indices, MultiIndex): # if constructed from repr
            self._indices = indices
        else:
            # Allowing Axis or FixedIndex here would make no sense
            ufl_assert(all(isinstance(ind, Index) for ind in indices))
            self._indices = MultiIndex(indices, len(indices))
        ufl_assert(all(isinstance(i, Index) for i in self._indices),
            "Expecting indices to be tuple of Index instances, not %s." % repr(indices))
        
        eset = set(expression.free_indices())
        iset = set(self._indices)
        freeset = eset - iset
        missingset = iset - eset
        self._free_indices = tuple(freeset)
        ufl_assert(len(missingset) == 0, "Missing indices %s in expression %s." % (missingset, expression))
        
        dims = expression.index_dimensions()
        self._index_dimensions = dict((i, dims[i]) for i in self._free_indices)
        
        self._shape = tuple(dims[i] for i in self._indices)
    
    def operands(self):
        return (self._expression, self._indices)
    
    def free_indices(self):
        return self._free_indices
    
    def index_dimensions(self):
        return self._index_dimensions
    
    def shape(self):
        return self._shape
    
    def __str__(self):
        return "[Rank %d tensor A, such that A_{%s} = %s]" % (self.rank(), self._indices, self._expression)
    
    def __repr__(self):
        return "ComponentTensor(%r, %r)" % (self._expression, self._indices)

# --- User-level functions to wrap expressions in the correct way ---

def as_tensor(expressions, indices = None):
    if indices is None:
        ufl_assert(isinstance(expressions, (list, tuple)),
            "Expecting nested list or tuple of Exprs.")
        return ListTensor(*expressions)
    ufl_assert(all(isinstance(ii, Index) for ii in indices),
               "Expecting sequence of Index objects.")
    return ComponentTensor(expressions, indices)

def as_matrix(expressions, indices = None):
    if indices is None:
        ufl_assert(isinstance(expressions, (list, tuple)),
            "Expecting nested list or tuple of Exprs.")
        ufl_assert(isinstance(expressions[0], (list, tuple)),
            "Expecting nested list or tuple of Exprs.")
        return ListTensor(*expressions)
    ufl_assert(all(isinstance(ii, Index) for ii in indices),
               "Expecting sequence of Index objects.")
    ufl_assert(len(indices) == 2, "Expecting exactly two indices.")
    return ComponentTensor(expressions, indices)

def as_vector(expressions, index = None):
    if index is not None:
        ufl_assert(isinstance(index, Index), "Expecting Index object.")
        index = (index,)
    return as_tensor(expressions, index)
