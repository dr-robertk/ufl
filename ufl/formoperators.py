"Various high level ways to transform a complete Form into a new Form."


__authors__ = "Martin Sandve Alnes"
__date__ = "2008-03-14 -- 2008-10-30"

from ufl.algorithms import compute_form_derivative
from ufl.algorithms import compute_form_adjoint, compute_form_action
from ufl.algorithms import compute_form_lhs, compute_form_rhs
#from ufl.algorithms import compute_dirichlet_functional

def rhs(form):
    """Given a combined bilinear and linear form,
    extract the linear form part (right hand side).

    TODO: Given "a = u*v*dx + f*v*dx, should this
    return "+f*v*dx" as found in the form or
    "-f*v*dx" as the rigth hand side should
    be when solving the equations?
    """
    return compute_form_rhs(form)

def lhs(form):
    """Given a combined bilinear and linear form,
    extract the bilinear form part (left hand side)."""
    return compute_form_lhs(form)

def action(form, function=None):
    """Given a bilinear form, return a linear form
    with an additional function coefficient, representing
    the action of the form on the function. This can be
    used for matrix-free methods."""
    return compute_form_action(form, function)

def adjoint(form):
    """Given a combined bilinear form, compute the adjoint
    form by swapping the test and trial functions."""
    return compute_form_adjoint(form)

def derivative(form, function, basisfunction=None):
    """Given any form, compute the linearization of the
    form with respect to the given discrete function.
    The resulting form has one additional basis function
    in the same finite element space as the function.
    A tuple of Functions may be provided in place of
    a single Function, in which case the new BasisFunction
    argument is based on a MixedElement created from this tuple."""
    return compute_form_derivative(form, function, basisfunction)

#def dirichlet_functional(form):
#    return compute_dirichlet_functional(form)

