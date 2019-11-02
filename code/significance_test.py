import numpy as np 
from random import shuffle

prob_a = 0.8741
prob_b = 0.8674
length_a = 1000
length_b = length_a

nr_sampling = 3000
alpha = 0.05

n_a = np.zeros(length_a)
n_b = np.zeros(length_b)

nr_ones_a = int(prob_a * length_a)
nr_ones_b = int(prob_b * length_b)

n_a[0:nr_ones_a] = 1
n_b[0:nr_ones_b] = 1

shuffle(n_a)
shuffle(n_b)

observed_mean = abs(prob_a - prob_b)
meassured_means = []
for i in range(nr_sampling):
    combined = np.concatenate((n_a, n_b))

    rand_permutation = np.random.permutation(combined)
    new_a = rand_permutation[0:length_a]
    new_b = rand_permutation[length_a:]

    mean_a = np.mean(new_a)
    mean_b = np.mean(new_b)
    meassured_means.append(abs(mean_a - mean_b))

meassured_means = np.array(meassured_means)
bigger_than_original = meassured_means > observed_mean

p_value = np.sum(bigger_than_original) / float(nr_sampling)
print("p_value", p_value)
print("alpha", alpha)
print("reject null_hypothesis (both come from same distribution)", p_value < alpha)
