# -*- coding: utf-8 -*-
"""
Created on Fri Jul 24 19:11:38 2015

@author: caro
"""

import numpy as np
import pandas as pd


class electrical_demand():
    '''
    '''
    def __init__(self, method, **kwargs):
        self.annual_demand = kwargs.get('annual_elec_demand')
        if self.annual_demand is None:
            self.annual_demand = self.calculate_annual_demand()

        self.decider(method, **kwargs)

    def decider(self, method, **kwargs):
        '''
        '''
        if method == 'csv':
            self.elec_demand = self.read_from_csv(path=
                                                  kwargs.get('path'),
                                                  filename=
                                                  kwargs.get('filename'))

        #TODO: implement
        elif method == 'db':
            conn = kwargs.get('conn')
            self.elec_demand = np.array([111, 222])

        elif method == 'scale_profile_csv':
            self.profile = self.read_from_csv(path=
                                              kwargs.get('path'),
                                              filename=
                                              kwargs.get('filename'))
            self.elec_demand = self.scale_profile()

        #TODO: implement
        elif method == 'scale_profile_db':
            conn = kwargs.get('conn')
            self.elec_demand = np.array([111, 222])

        #TODO: implement
        elif method == 'scale_entsoe':
            conn = kwargs.get('conn')
            self.elec_demand = np.array([111, 222])

        #TODO: implement
        elif method == 'calculate_profile':
            self.elec_demand = np.array([111, 222])

        return self.elec_demand

    def read_from_csv(self, **kwargs):
        '''
        read entire demand timeseries or only profile for further
        processing from csv
        '''
        self.profile = pd.read_csv(kwargs.get('path') +
                                   kwargs.get('filename'),
                                   sep=",")

        self.year = 2010  # TODO: year temporarily

        self.profile = self.profile['deu_' + str(self.year)]

        return self.profile

    def read_from_db(self):
        '''
        read entire demand timeseries or only profile for further
        processing from database
        '''
        return

    def read_entsoe(self):
        return

    def scale_profile(self):
        '''
        scale a given profile to a given annual demand, which is the sum
        of the single profile values
        '''
        self.elec_demand = (self.profile /
                            self.profile.sum() *
                            self.annual_demand)
        return self.elec_demand

    def calculate_annual_demand(self):
        '''
        calculate annual demand from statistic data
        '''
        self.annual_demand = 50 + 50
        return self.annual_demand


class heat_demand():
    # Das Gebäudeprofil kommt aus der Datenbank einer Datei oder einer anderen
    # Funktion.
    pass
