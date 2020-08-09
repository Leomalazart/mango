"""
Meta Tuner Class: Used to optimize across a set of models:
- selecting intelligently the order of functions to optimize

Used the other abstractions.

Current implementation: Bare Metal functionality for testing.

ToDo: Improve code with better config management and remove hardcoded parameters
"""

from dataclasses import dataclass
from mango.domain.domain_space import domain_space
from mango.optimizer.bayesian_learning import BayesianLearning
from scipy.stats._distn_infrastructure import rv_frozen

from tqdm.auto import tqdm
import numpy as np

## setting warnings to ignore for now
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import random

np.random.seed(0)
random.seed(0)

class MetaTuner:

    def __init__(self,param_dict_list, objective_list):
        self.param_dict_list = param_dict_list
        self.objective_list = objective_list

        #list of GPR for each objective
        self.gpr_list = []

        # store the results of MetaTuner
        self.results = dict()

        #batch size of the entire metaTuner
        self.batch_size = 1

        #batch size per function to select
        self.obj_batch_size = 1

        self.num_of_iterations = 20

        #use to see the info when metaTuner is running
        self.debug = False

        #stores the index of evaluated objectives
        self.objectives_evaluated = []

    def run(self):
        #run the metaTuner
        self.results = self.runExponentialTuner()
        return self.results



    def runExponentialTuner(self):
        """
        Steps:
        1-Create DS obj for each obj of param_dict_list
        2-Sample randomly from the DS objects and evaluate the objective functions.
        3- Now use the GPR for each objective to select next batch
        4- Select the best values based on surrogate from GPR.
        5- Exponentially scale the surrogate exploration factor for non-selected functions.
        """

        num_of_random = 2


        ds = []
        for i in self.param_dict_list:
            ds.append(domain_space(i,100))


        X_dict_list = {}
        Y_dict_list = {}

        X_dict_array = {}
        Y_dict_array = {}

        #stores the maximum value of the objective function for each objective
        Y_dict_array_max = {}


        #randomly evaluate the initial points for objectives
        for i in range(len(self.param_dict_list)):
            ds_i = ds[i]
            random_hyper_parameters = ds_i.get_random_sample(num_of_random)

            y_list = self.objective_list[i](random_hyper_parameters)

            x_list = random_hyper_parameters

            #print(i, random_hyper_parameters, x_list, y_list)

            X_dict_list[i] =[]
            X_dict_list[i].append(x_list)

            Y_dict_list[i] =[]
            Y_dict_list[i].append(y_list)

            x_array = ds_i.convert_GP_space(random_hyper_parameters)
            X_dict_array[i] = x_array

            y_array = np.array(y_list).reshape(len(y_list),1)
            Y_dict_array[i] = y_array

            #the random ones are added as it is
            Y_dict_array_max[i] = y_array



        #print("Debug")
        #print('Random Values Tried X_dict_array')
        #print(X_dict_array)
        #print('*'*10, "Y_dict_array")
        #print('*')
        #print(Y_dict_array)
        #print('*'*100)

        #Initialize the number of Optimizers
        Optimizer_list = []

        for i in range(len(self.objective_list)):
            Optimizer_i = BayesianLearning()
            Optimizer_list.append(Optimizer_i)


        # Storing exponential exploration factors of optimizers
        Optimizer_exploration = []
        for i in range(len(self.objective_list)):
            Optimizer_exploration.append(1.0)


        #print(Optimizer_exploration)

        #Now run the optimization iterations
        for itr in range(self.num_of_iterations):


            #next values of x returned from individual function
            #dimensions of x are dependent on types of param dict, so using a list
            x_values_list = []

            #Next promising regions surrogate values
            s_values_array = np.empty((0,1), float)


            #keeping track of objective indices
            x_obj_indices = []


            #sample individual domains and evaluate surrogate functions.
            #we get the next promising samples along with the surrogate function values
            for j in range(len(ds)):
                domain_list = ds[j].get_domain()
                X_domain_np = ds[j].convert_GP_space(domain_list)

                #next batch of x for this objective along with its surrogate value
                X_next_batch, s_values = Optimizer_list[j].get_next_batch_MetaTuner(X_dict_array[j],Y_dict_array[j],X_domain_np, self.obj_batch_size, Optimizer_exploration[j])

                s_values_array = np.append(s_values_array, s_values)

                x_values_list = x_values_list + X_next_batch

                #keep track of objective function for corresponding surrogate and x values
                for k in range(self.obj_batch_size):
                    x_obj_indices.append(j)


            #print(x_values_list, s_values_array, x_obj_indices )

            #sort the surrogate values in descending order, to select the best value from them
            v_sorting_index = np.argsort(-s_values_array, axis=0)

            #now select the self.batch_size values from x_values_list based on v_sorting_index
            v_sorting_index = v_sorting_index[:self.batch_size]

            #keep track of objective indices selected in current iteration
            loc_indices = []

            for i in range(v_sorting_index.shape[0]):
                curr_x_next_np = x_values_list[v_sorting_index[i]]

                #convert this into the parameter space for scheduling
                #see the function index for this x value
                index = x_obj_indices[v_sorting_index[i]]

                #keep track of local indices
                loc_indices.append(index)

                #keep track of indices in a global datastr for visualization of function selection
                self.objectives_evaluated.append(index)

                #In parameter space
                curr_x_next = ds[index].convert_PS_space(curr_x_next_np)

                #print(curr_x_next_np, curr_x_next, curr_x_next_np.shape)

                #run the next curr_x_next value for the objective function
                y_list = self.objective_list[index](curr_x_next)
                curr_y_array = np.array(y_list).reshape(len(y_list), 1)
                #append the curr_x_next_np, curr_x_next, y_list to appropriate datastructures for book keeping

                X_dict_array[index] = np.vstack((X_dict_array[index], curr_x_next_np))
                Y_dict_array[index] = np.vstack((Y_dict_array[index], curr_y_array))

                Y_dict_array_max[index] = np.vstack((Y_dict_array_max[index], np.max(Y_dict_array[index])))


            #scale the exploration of objectives that are not selected for others make their exploration to 1
            for i in range(len(self.objective_list)):
                if i in loc_indices:
                    Optimizer_exploration[i] = 1.0
                else:
                    Optimizer_exploration[i] = Optimizer_exploration[i]*2.0

            #print(itr, loc_indices,  Optimizer_exploration, s_values_array)

        self.X_dict_array = X_dict_array
        self.Y_dict_array = Y_dict_array
        self.Y_dict_array_max = Y_dict_array_max