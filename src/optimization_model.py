import pyomo.environ as po
import generic as gc
from network.entities import Bus, Component
import network.entities.components as cp


class OptimizationModel(po.ConcreteModel):
    """Create Pyomo model of the energy system.

    Parameters
    ----------
    entities : list with all entity objects
    timesteps : list with all timesteps as integer values
    invest : boolean

    Returns
    -------
    m : pyomo.ConcreteModel

    """

    def __init__(self, entities, timesteps, options=None):

        super().__init__()

        self.entities = entities
        self.timesteps = timesteps
        self.invest = options.get("invest", False)
        self.slack = options.get("slack", True)

        # calculate all edges ([('coal', 'pp_coal'),...])
        self.all_edges = self.edges([e for e in self.entities
                                     if isinstance(e, Component)])

        gc.generic_variables(model=self, edges=self.all_edges,
                             timesteps=self.timesteps)

        # list with all necessary classes
        component_classes = (cp.Transformer.__subclasses__() +
                             cp.Sink.__subclasses__() +
                             cp.Source.__subclasses__() +
                             cp.Transport.__subclasses__())

        # set attributes lists per class with objects and uids for opt model
        for cls in component_classes:
            objs = [e for e in self.entities if isinstance(e, cls)]
            uids = [e.uid for e in objs]
            setattr(self, cls.lower_name + "_objs", objs)
            setattr(self, cls.lower_name + "_uids", uids)
            # "call" methods to add the constraints opt. problem
            if objs:
                getattr(self, cls.lower_name + "_model")(objs=objs, uids=uids)

        self.bus_model()
        self.objective()



    def bus_model(self):
        """bus model creates bus balance for all buses using pyomo.Constraint

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        self.bus_objs = [e for e in self.entities if isinstance(e, Bus)]
        self.bus_uids = [e.uid for e in self.bus_objs]

        bus_objs = [obj for obj in self.bus_objs
                    if any([obj.type == "el", obj.type == "th"])]
        bus_uids = [obj.uid for obj in bus_objs]

        # slack variables that assures a feasible problem
        if self.slack is True:
            self.shortage_slack = po.Var(self.bus_uids, self.timesteps,
                                         within=po.NonNegativeReals)
            self.excess_slack = po.Var(self.bus_uids, self.timesteps,
                                       within=po.NonNegativeReals)

        I = {b.uid: [i.uid for i in b.inputs] for b in bus_objs}
        O = {b.uid: [o.uid for o in b.outputs] for b in bus_objs}

        # constraint for bus balance:
        # component inputs/outputs are negative/positive in the bus balance
        def bus_rule(self, e, t):
            expr = 0
            expr += -sum(self.w[e, o, t] for o in O[e])
            expr += sum(self.w[i, e, t] for i in I[e])
            if self.slack is True:
                expr += -self.excess_slack[e, t] + self.shortage_slack[e, t]
            return(expr, 0)
        self.bus = po.Constraint(bus_uids, self.timesteps, rule=bus_rule)

        # select only buses that are resources (gas, oil, etc.)
        rbus_objs = [obj for obj in self.bus_objs
                     if all([obj.type != "el", obj.type != "th"])]
        rbus_uids = [e.uid for e in rbus_objs]

        # set limits for resource buses
        gc.generic_limit(model=self, objs=rbus_objs, uids=rbus_uids,
                         timesteps=self.timesteps)

    def simple_transformer_model(self, objs, uids):
        """Generic transformer model containing the constraints
        for generic transformer components.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """

        gc.generic_io_constraints(model=self, objs=objs, uids=uids,
                                  timesteps=self.timesteps)

        # set bounds for variables  models
        gc.generic_w_ub(model=self, objs=objs, uids=uids,
                        timesteps=self.timesteps)

    def simple_chp_model(self, objs, uids):
        """Simple chp model containing the constraints for simple chp
        components.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel

        """
        # use generic_transformer model for in-out relation and
        # upper/lower bounds
        self.simple_transformer_model(objs=objs, uids=uids)

        # set with output uids for every simple chp
        # {'pp_chp': ['b_th', 'b_el']}
        O = {obj.uid: [o.uid for o in obj.outputs[:]] for obj in objs}
        # efficiencies for simple chps
        eta = {obj.uid: obj.eta for obj in objs}

        # additional constraint for power to heat ratio of simple chp comp:
        # P/eta_el = Q/eta_th
        def chp_rule(self, e, t):
            expr = self.w[e, O[e][0], t] / eta[e][0]
            expr += -self.w[e, O[e][1], t] / eta[e][1]
            return(expr == 0)
        self.simple_chp = po.Constraint(uids, self.timesteps, rule=chp_rule)

    def simple_extraction_chp_model(self, objs, uids):
        """Simple extraction chp model containing the constraints for
        objects of class cp.SimpleExtractionCHP().

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel

        """
        # {'pp_chp': 'gas'}
        I = {obj.uid: obj.inputs[0].uid for obj in objs}
        # set with output uids for every simple chp
        # {'pp_chp': ['b_th', 'b_el']}
        O = {obj.uid: [o.uid for o in obj.outputs[:]]
             for obj in objs}
        k = {obj.uid: obj.k for obj in objs}
        c = {obj.uid: obj.c for obj in objs}
        beta = {obj.uid: obj.beta for obj in objs}
        p = {obj.uid: obj.p for obj in objs}
        out_min = {obj.uid: obj.out_min
                   for obj in objs}

        # constraint for transformer energy balance:
        # 1) P <= p[0] - beta[0]*Q
        def c1_rule(self, e, t):
            expr = self.w[e, O[e][0], t]
            rhs = p[e][0] - beta[e][0] * self.w[e, O[e][1], t]
            return(expr <= rhs)
        self.simple_extraction_chp_1 = \
            po.Constraint(uids, self.timesteps,
                          rule=c1_rule)

        # 2) P = c[0] + c[1] * Q
        def c2_rule(self, e, t):
            expr = self.w[e, O[e][1], t]
            rhs = (self.w[e, O[e][0], t] - c[e][0]) / c[e][1]
            return(expr <= rhs)
        self.simple_extraction_chp_2 = \
            po.Constraint(uids, self.timesteps,
                          rule=c2_rule)

        # 3) P >= p[1] - beta[1]*Q
        def c3_rule(self, e, t):
            if out_min[e] > 0:
                expr = self.w[e, O[e][0], t]
                rhs = p[e][1] - beta[e][1] * self.w[e, O[e][1], t]
                return(expr >= rhs)
            else:
                return(po.Constraint.Skip)
        self.simple_extraction_chp_3 = \
            po.Constraint(uids, self.timesteps,
                          rule=c3_rule)

        # H = k[0] + k[1]*P + k[2]*Q
        def in_out_rule(self, e, t):
            expr = 0
            expr += self.w[I[e], e, t]
            expr += - (k[e][0] + k[e][1]*self.w[e, O[e][0], t] +
                       k[e][2]*self.w[e, O[e][1], t])
            return(expr, 0)
        self.simple_extraction_chp_io = \
            po.Constraint(uids, self.timesteps,
                          rule=in_out_rule)

    def fixed_source_model(self, objs, uids):
        """fixed source model containing the constraints for
        fixed sources.

        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        if self.invest is False:
            gc.generic_fixed_source(model=self, objs=objs, uids=uids,
                                    timesteps=self.timesteps)
        else:
            gc.generic_fixed_source_invest(model=self, objs=objs, uids=uids,
                                           timesteps=self.timesteps)

    def dispatch_source_model(self, objs, uids):
        """
        """
        if self.invest is False:
            gc.generic_dispatch_source(model=self, objs=objs, uids=uids,
                                       timesteps=self.timesteps)

    def simple_sink_model(self, objs, uids):
        """simple sink model containing the constraints for simple sinks
        Parameters
        ----------
        self : pyomo.ConcreteModel

        Returns
        -------
        self : pyomo.ConcreteModel
        """
        gc.generic_fixed_sink(model=self, objs=objs, uids=uids,
                              timesteps=self.timesteps)

    def simple_storage_model(self, objs, uids):
        """Simple storage model containing the constraints for simple storage
        components.

        Parameters
        ----------
        m : pyomo.ConcreteModel

        Returns
        -------
        m : pyomo.ConcreteModel
        """

        O = {obj.uid: obj.outputs[0].uid for obj in objs}
        I = {obj.uid: obj.inputs[0].uid for obj in objs}

        # set bounds for basic/investment models
        if(self.invest is False):
            ee = self.edges(objs)
            # installed input/output capacity
            for (e1, e2) in ee:
                for t in self.timesteps:
                    self.w[e1, e2, t].setub(10)
                    self.w[e1, e2, t].setlb(1)
        else:
            # constraint for additional capacity in investment models
            def invest_rule(self, e, t):
                return(self.soc_v[e, t] <= self.soc_max[e] + self.soc_add_v[e])
            self.soc_max_c = po.Constraint(uids, self.timesteps,
                                           rule=invest_rule)

        # storage energy balance
        def storage_balance_rule(self, e, t):
            if(t == 0):
                expr = 0
                expr += self.soc_v[e, t]
                return(expr, 0)
            else:
                expr = self.soc_v[e, t]
                expr += - self.soc_v[e, t-1] - self.w[I[e], e, t] + \
                    self.w[e, O[e], t]
                return(expr, 0)
            self.simple_storage_c = po.Constraint(uids, self.timesteps,
                                                  rule=storage_balance_rule)

    def simple_transport_model(self, objs, uids):
        """Simple transport model building the constraints
        for simple transport components

        Parameters
        ----------
        m : pyomo.ConcreteModel

        Returns
        -------
        m : pyomo.ConcreteModel
        """

        self.simple_transformer_model(objs=objs, uids=uids)

    def objective(self):
        """Function that creates the objective function of the optimization
        model.

        Parameters
        ----------
        m : pyomo.ConcreteModel

        Returns
        -------
        m : pyomo.ConcreteModel
        """

        # create a combine list of all cost-related components
        objective_objs = (
            self.simple_chp_objs +
            self.simple_transformer_objs +
            self.simple_storage_objs +
            self.simple_transport_objs)

        self.objective_uids = (
            self.simple_chp_uids +
            self.simple_transformer_uids +
            self.simple_transport_uids)

        I = {obj.uid: obj.inputs[0].uid for obj in objective_objs}
        # operational costs
        self.opex_var = {obj.uid: obj.opex_var for obj in objective_objs}
        self.fuel_costs = {obj.uid: obj.inputs[0].price
                           for obj in objective_objs}
        # get dispatch expenditure for renewable energies with dispatch
        self.dispatch_ex = {obj.uid: obj.dispatch_ex
                            for obj in self.dispatch_source_objs}

        # objective function
        def obj_rule(self):
            expr = 0
            expr += sum(self.w[I[e], e, t] * (self.opex_var[e] +
                                              self.fuel_costs[e])
                        for e in self.objective_uids
                        for t in self.timesteps)
            if self.slack is True:
                expr += sum(self.shortage_slack[e, t] * 10e10
                            for e in self.bus_uids for t in self.timesteps)

            expr += sum(self.dispatch[e, t] * self.dispatch_ex[e]
                        for e in self.dispatch_source_uids
                        for t in self.timesteps)
            # add additional capacity & capex for investment models
            if(self.invest is True):
                self.capex = {obj.uid: obj.capex for obj in objective_objs}

                expr += sum(self.add_cap[I[e], e] * self.capex[e]
                            for e in self.objective_uids)
                expr += sum(self.soc_add[e] * self.capex[e]
                            for e in self.simple_storage_uids)
            return(expr)
        self.objective = po.Objective(rule=obj_rule)

    def solve(self, solver='glpk', solver_io='lp', debug=False,
              results_to_objects=True, **kwargs):
        """Method that creates the instance of the model and solves it.

        Parameters
        ----------
        self : pyomo.ConcreteModel
        solver str: solver to be used e.g. 'glpk','gurobi','cplex'
        solver_io str: str that defines the solver interaction
        (file or interface) 'lp','nl','python'
        result_to_objects boolean: Flag if results from optimization problem
        are written back to objects
        **kwargs: other arguments for the pyomo.opt.SolverFactory.solve()
        method

        Returns
        -------
        self : solved pyomo.ConcreteModel instance
        """

        from pyomo.opt import SolverFactory

        # create model instance
        instance = self.create()

        # write lp-file
        if(debug is True):
            instance.write('problem.lp',
                           io_options={'symbolic_solver_labels': True})
            # print instance
            # instance.pprint()
        # solve instance
        opt = SolverFactory(solver, solver_io=solver_io)
        # store results
        results = opt.solve(instance, **kwargs)
        # load results back in instance
        instance.load(results)

        if results_to_objects is True:
            for entity in self.entities:

                if (isinstance(entity, cp.Transformer) or
                        isinstance(entity, cp.Source)):
                    # write outputs
                    O = [e.uid for e in entity.outputs[:]]
                    for o in O:
                        entity.results['out'][o] = []
                        for t in self.timesteps:
                            entity.results['out'][o].append(
                                self.w[entity.uid, o, t].value)

                    I = [i.uid for i in entity.inputs[:]]
                    for i in I:
                        entity.results['in'][i] = []
                        for t in self.timesteps:
                            entity.results['in'][i].append(
                                self.w[i, entity.uid, t].value)

                # write results to self.simple_sink_objs
                # (will be the value of simple sink in general)
                if isinstance(entity, cp.Sink):
                    i = entity.inputs[0].uid
                    entity.results['in'][i] = []
                    for t in self.timesteps:
                        entity.results['in'][i].append(
                            self.w[i, entity.uid, t].value)

            if(self.invest is True):
                for entity in self.entities:
                    if isinstance(entity, cp.Transformer):
                        entity.results['add_cap_out'] = \
                            self.add_cap[entity.uid,
                                         entity.outputs[0].uid].value
                    if isinstance(entity, cp.Source):
                        entity.results['add_cap_out'] = \
                            self.add_cap[entity.uid,
                                         entity.outputs[0].uid].value
                    if isinstance(entity, cp.transformers.Storage):
                        entity.results['add_cap_soc'] = \
                            self.soc_add[entity.uid].value

        return(instance)

    def edges(self, components):
        """Method that creates a list with all edges for the objects in
        components.

        Parameters
        ----------
        self :
        components : list of component objects

        Returns
        -------
        edges : list with tupels that represent the edges
        """

        edges = []
        # create a list of tuples
        # e.g. [('coal', 'pp_coal'), ('pp_coal', 'b_el'),...]
        for c in components:
            for i in c.inputs:
                ei = (i.uid, c.uid)
                edges.append(ei)
            for o in c.outputs:
                ej = (c.uid, o.uid)
                edges.append(ej)
        return(edges)




def io_sets(components):
    """Function that gets inputs and outputs for given components.

    Parameters
    ----------
    components : list of component objects

    Returns
    -------
    (I, O) : lists with tupels that represent the edges
    """
    O = {obj.uid: [o.uid for o in obj.outputs[:]] for obj in components}
    I = {obj.uid: [i.uid for i in obj.inputs[:]] for obj in components}
    return(I, O)
