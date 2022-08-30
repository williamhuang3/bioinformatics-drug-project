#William Huang
#Bioinformatics Data Project
#Dependencies: ChemBL and rdkit (conda install -c rdkit rdkit -y)
# Bash: conda install -c conda-forge bash
import pandas as pd
import numpy as np
from chembl_webresource_client.new_client import new_client
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski
from lipinski_plots import lipinski_plots as lp
from numpy.random import seed
from numpy.random import randn
from scipy.stats import mannwhitneyu
import matplotlib.pyplot as plt
import subprocess
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import VarianceThreshold
import seaborn as sns
sns.set(style='ticks')
import matplotlib.pyplot as plt

def retrievedata():
    target = new_client.target
    target_query = target.search('coronavirus')
    targets = pd.DataFrame.from_dict(target_query)
    selected_target = targets.target_chembl_id[1]
    activity = new_client.activity
    res = activity.filter(target_chembl_id=selected_target).filter(standard_type="IC50")
    df = pd.DataFrame.from_dict(res)
    if df.empty:
        print("No IC50 vals.")
        return
    df2 = df[df.standard_value.notna()]
    print(len(df2))
    df2 = df2.loc[df2.standard_value != '0.0']
    print(len(df2))
    df2 = df2[df.canonical_smiles.notna()]
    df2 = df2.drop_duplicates(['canonical_smiles'])
    preprocess(df2)

def preprocess(df2):
    selection = ['molecule_chembl_id', 'canonical_smiles', 'standard_value']
    df3 = df2[selection]
    df3.to_csv('bioactivity_data_preprocessed.csv', index=False)
    labelcompounds(df3)
10
def labelcompounds(df):
    bioactivity_threshold = []
    for i in df.standard_value:
        if float(i) >= 10000:
            bioactivity_threshold.append("inactive")
        elif float(i) <= 1000:
            bioactivity_threshold.append("active")
        else:
            bioactivity_threshold.append("intermediate")
    bioactivity_class = pd.Series(bioactivity_threshold, name='class')
    df.reset_index(drop=True, inplace=True)
    df2 = pd.concat([df, bioactivity_class], axis=1)
    df_no_smiles = df2.drop(columns='canonical_smiles')
    smiles = []

    for i in df.canonical_smiles.tolist():
        cpd = str(i).split('.')
        cpd_longest = max(cpd, key=len)
        smiles.append(cpd_longest)

    smiles = pd.Series(smiles, name='canonical_smiles')
    df_cleaned_smiles = pd.concat([df_no_smiles, smiles], axis=1)
    evaluate_drug(df2, df_cleaned_smiles)

def evaluate_drug(df, df_cleaned_smiles):
    #appends lipinski descriptors to dataframe
    df_lipinski = lipinski_descriptors(df_cleaned_smiles.canonical_smiles)
    df_combined = pd.concat([df, df_lipinski], axis=1)

    #normalizes the IC50
    df_normal = norm_values(df_combined)
    #turns IC50 to pIC50
    df_final = to_pIC50(df_normal)

    df_final.to_csv('bioactivity_data_final.csv', index=False)
    df_2class = df_final[df_final['class'] != 'intermediate']
    lipinskiplot = lp(df_2class)
    lipinskiplot.bar_graph(df_2class)
    lipinskiplot.scatter_plot(df_2class)
    lipinskiplot.pIC_50_plot(df_2class)
    print(mannwhitney(df, df_2class, 'pIC50'))
    lipinskiplot.mol_weight(df_2class)
    print(mannwhitney(df, df_2class, 'MW'))
    lipinskiplot.logP(df_2class)
    print(mannwhitney(df, df_2class, 'LogP'))
    lipinskiplot.num_hdonors(df_2class)
    print(mannwhitney(df, df_2class, 'NumHDonors'))
    lipinskiplot.num_hacceptors(df_2class)
    print(mannwhitney(df, df_2class, 'NumHAcceptors'))

def to_pIC50(input):
    pIC50 = []

    for i in input['standard_value_norm']:
        molar = i * (10 ** -9)  # Converts nM to M
        pIC50.append(-np.log10(molar))

    input['pIC50'] = pIC50
    x = input.drop('standard_value_norm', 1)

    return x


def norm_values(input):
    norm = []

    for i in input['standard_value']:
        i = float(i)
        if i > 100000000:
            i = 100000000
        norm.append(i)

    input['standard_value_norm'] = norm
    x = input.drop('standard_value', 1)

    return x

def lipinski_descriptors(smiles, verbose=False):
    # Inspired by: https://codeocean.com/explore/capsules?query=tag:data-curation
    moldata = []
    for elem in smiles:
        mol = Chem.MolFromSmiles(elem)
        moldata.append(mol)

    baseData = np.arange(1, 1)
    i = 0
    for mol in moldata:

        desc_MolWt = Descriptors.MolWt(mol)
        desc_MolLogP = Descriptors.MolLogP(mol)
        desc_NumHDonors = Lipinski.NumHDonors(mol)
        desc_NumHAcceptors = Lipinski.NumHAcceptors(mol)

        row = np.array([desc_MolWt,
                        desc_MolLogP,
                        desc_NumHDonors,
                        desc_NumHAcceptors])

        if (i == 0):
            baseData = row
        else:
            baseData = np.vstack([baseData, row])
        i = i + 1

    columnNames = ["MW", "LogP", "NumHDonors", "NumHAcceptors"]
    descriptors = pd.DataFrame(data=baseData, columns=columnNames)

    return descriptors


def mannwhitney(df, df_2class, descriptor, verbose=False):
    # https://machinelearningmastery.com/nonparametric-statistical-significance-tests-in-python/
    # seed the random number generator
    seed(1)

    # actives and inactives
    selection = [descriptor, 'class']
    df = df_2class[selection]
    active = df[df['class'] == 'active']
    active = active[descriptor]

    selection = [descriptor, 'class']
    df = df_2class[selection]
    inactive = df[df['class'] == 'inactive']
    inactive = inactive[descriptor]

    # compare samples
    stat, p = mannwhitneyu(active, inactive)
    # print('Statistics=%.3f, p=%.3f' % (stat, p))

    # interpret
    alpha = 0.05
    if p > alpha:
        interpretation = 'Same distribution (fail to reject H0)'
    else:
        interpretation = 'Different distribution (reject H0)'

    results = pd.DataFrame({'Descriptor': descriptor,
                            'Statistics': stat,
                            'p': p,
                            'alpha': alpha,
                            'Interpretation': interpretation}, index=[0])
    filename = 'mannwhitneyu_' + descriptor + '.csv'
    results.to_csv(filename, index=False)

    return results

def predict_from_pIC50():
    df = pd.read_csv('bioactivity_data_final.csv')
    selection = ['canonical_smiles', 'molecule_chembl_id']
    df_selection = df[selection]
    df_selection.to_csv('molecule.smi', sep='\t', index=False, header=False)
    subprocess.run(["python.exe",".\padel.sh"])
    X = pd.read_csv('descriptors_output.csv').drop(columns=['Name'])
    Y = df['pIC50']
    #relating pIC50 to the molecular descriptors
    dataset = pd.concat([X, Y], axis=1)
    dataset.tocsv('bioactivity_data_pubchem_padel.csv')
    selection = VarianceThreshold(threshold=(.8 * (1 - .8)))
    X = selection.fit_transform(X)
    X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2)
    model = RandomForestRegressor(n_estimators=100)
    model.fit(X_train, Y_train)
    r2 = model.score(X_test, Y_test)
    predictions = model.predict(X_test)

    sns.set(color_codes=True)
    sns.set_style("white")

    ax = sns.regplot(Y_test, predictions, scatter_kws={'alpha': 0.4})
    ax.set_xlabel('Experimental pIC50', fontsize='large', fontweight='bold')
    ax.set_ylabel('Predicted pIC50', fontsize='large', fontweight='bold')
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 12)
    ax.figure.set_size_inches(5, 5)
    plt.show

if __name__ == '__main__':
    retrievedata()
    predict_from_pIC50()


