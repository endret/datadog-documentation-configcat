#!/usr/bin/env python3
from optparse import OptionParser
from os.path import splitext, exists, basename, curdir, join, abspath, normpath, dirname
from os import sep, makedirs, getenv
from tqdm import *
import yaml
import requests
import tempfile
import csv
import glob
import fileinput
import json

"""
Variables
"""
DESC_TOKEN = "{{< get-desc-from-git >}}"
DESC_ATTRIBUTE = "short_description"

"""
Functions
"""

def replace_token(to_path, key_name, content_token, data):
    """
    Inline the content of data instead of the content_token in an integration content file

    :param to_path:                 the output path to yaml files
    :param key_name:        integration key name for root object
    :param content_token:   token to find and replace inside the file
    :param data:            data to inline in the file
    """

    # Read in the file
    with open('{}{}.md'.format(to_path,key_name), 'r') as file :
        print('opening {}.md'.format(key_name))
        filedata = file.read()

    # Replace the target string
    filedata = filedata.replace(content_token, data)

    # Write the file out again
    with open('{}{}.md'.format(to_path,key_name), 'w') as file:
        print('writing {}.md'.format(key_name))
        file.write(filedata)

def file_update_content(to_path, key_name, data_array):
    """
    Take an integration file and inline all token inside
    
    :param to_path:         the output path to yaml files
    :param key_name:        integration key name for root object
    :param data_array:  Array of data to inline, array of tuple {"content_token":"data"}
    """ 
    for obj in data_array:
        replace_token(to_path, key_name,obj[0],obj[1])


def manifest_get_data(to_path,key_name,attribute):
    """
    Extract an attribute value from the manifest of an integration
    
    :param to_path:     the output path to yaml files
    :param key_name:    integration key name for root object
    :param attribute:   attribute to get data from
    """ 
    with open('{}{}_manifest.json'.format(to_path, key_name)) as manifest:
        manifest_json = json.load(manifest)
        return manifest_json[attribute]

def update_integration_pre_build(from_path=None, to_path=None):
    """
  All modifications that may happen to a integration content are here
    
    
    """
    
    if exists(from_path):
        pattern = '**/*_manifest.json'
        for file_name in tqdm(sorted(glob.glob('{}{}'.format(from_path, pattern), recursive=True))):
            key_name = basename(file_name.replace('_manifest.json', ''))
            """
            Gathering the manifest short description and inlining it to the description param for a given integration
            """
            data_array=[]
            data_array.append([DESC_TOKEN,manifest_get_data(from_path,key_name,DESC_ATTRIBUTE)])

            print('Updating integrations description...')
            file_update_content(to_path, key_name, data_array)
    else:
        print('Path does not exist: {}'.format(from_path))
        exit(1)

def csv_to_yaml(key_name, csv_filename, yml_filename):
    """
    Given a file path to a single csv file convert it to a yaml file

    :param key_name: integration key name for root object
    :param csv_filename: path to input csv file
    :param yml_filename: path to output yml file
    """
    yaml_data = {key_name: []}
    with open(csv_filename) as csv_file:
        reader = csv.DictReader(csv_file, delimiter=',')
        yaml_data[key_name] = [dict(line) for line in reader]
    if yaml_data[key_name]:
        with open(file=yml_filename, mode='w', encoding='utf-8') as f:
            f.write(yaml.dump(yaml_data, default_flow_style=False))


def download_github_files(token, org, repo, branch, to_path, is_dogweb=False):
    """
    Using the github api downloads csv files to a temporary location for processing

    :param token: string of github token
    :param org: string of organization
    :param repo: string of git repository
    :param branch: string of branchname
    :param to_path: where to extract
    :param is_dogweb: if dogweb repo we need to get nested data
    """
    directory = 'integration' if is_dogweb else ''
    url = 'https://api.github.com/repos/{0}/{1}/contents/{3}?ref={2}'.format(org, repo, branch, directory)
    headers = {'Authorization': 'token {}'.format(token)} if token else {}
    excludes = ['LICENSE', 'Rakefile', 'Gemfile']
    print('Downloading files from {}/{}..'.format(repo, branch))
    response = requests.get(url, headers=headers)

    """
    Donwloading metadata.csv
    """
    if response.status_code == requests.codes.ok:
        for obj in tqdm(response.json()):
            name = obj.get('name', '')
            if not name.startswith('.') and not splitext(name)[1] and name not in excludes:
                to_csv = '{0}/{1}/{1}_metadata.csv'.format(directory, name) if is_dogweb else '{}/metadata.csv'.format(
                    name)
                response_csv = requests.get(
                    'https://raw.githubusercontent.com/{0}/{1}/{2}/{3}'.format(org, repo, branch, to_csv),
                    headers=headers
                )
                if response_csv.status_code == requests.codes.ok:
                    with open('{}{}.csv'.format(to_path, name), mode='wb+') as f:
                        f.write(response_csv.content)
    
    """
    Donwloading manifest.json for integrations core repo only
    """
    if ((response.status_code == requests.codes.ok) and (not is_dogweb)):
        for obj in tqdm(response.json()):
            name = obj.get('name', '')
            if not name.startswith('.') and not splitext(name)[1] and name not in excludes:
                to_manifest = '{}/manifest.json'.format(name)
                response_manifest = requests.get(
                    'https://raw.githubusercontent.com/{0}/{1}/{2}/{3}'.format(org, repo, branch, to_csv),
                    headers=headers
                )
                if response_manifest.status_code == requests.codes.ok:
                    with open('{}{}_manifest.json'.format(to_path, name), mode='wb+') as f:
                        print('Creating manifest for {} in {}'.format(name,to_path))
                        f.write(response_manifest.content)


    else:
        print('There was an error ({}) listing {}/{} contents..'.format(response.status_code, repo, branch))
        exit(1)



def sync_from_dir(from_path=None, to_path=None, is_dogweb=False):
    """
    Sync csv files to yaml files based on input and output directories

    :param from_path: the input path to csv files
    :param to_path: the output path to yaml files
    """
    print('Syncing integrations...')
    if exists(from_path):
        pattern = '**/*.csv'
        if is_dogweb:
            pattern = 'integration/**/*.csv'
        for file_name in tqdm(sorted(glob.glob('{}{}'.format(from_path, pattern), recursive=True))):
            key_name = basename(file_name.replace('.csv', ''))
            if key_name.endswith('_metadata'):
                key_name = basename(key_name.replace('_metadata', ''))
            if key_name == 'metadata':
                key_name = basename(dirname(normpath(file_name)))
            new_file_name = '{}{}.yaml'.format(to_path, key_name)
            csv_to_yaml(key_name, file_name, new_file_name)
    else:
        print('Path does not exist: {}'.format(from_path))
        exit(1)



def parse_args(args=None):
    """
    Given a list of arguments parse them using ArgumentParser

    :param args: list of arguments
    :return: instance of tuple of values and arguments
    """
    parser = OptionParser(usage="usage: %prog [options] link_type")
    parser.add_option("-t", "--token", help="github access token", default=None)
    parser.add_option("-w", "--dogweb", help="path to dogweb local folder", default=None)
    parser.add_option("-i", "--integrations", help="path to integrations-core local folder", default=None)
    parser.add_option("-s", "--source", help="location of src files", default=curdir)
    return parser.parse_args(args)


def sync(*args):
    """
    Given optional arguments generate yaml integration data from dogweb / integrations-core
    using either local or remote data

    :param args: list of arguments
    """

    # collect arguments
    options, args = parse_args(*args)

    # attempt to get token from env vars, take explicit arg over envs
    options.token = getenv('GITHUB_TOKEN', options.token) if not options.token else options.token

    # setup path variables
    extract_path = '{}'.format(join(tempfile.gettempdir(), "extracted") + sep)
    dogweb_extract_path = '{}'.format(extract_path + 'dogweb' + sep)
    integrations_extract_path = '{}'.format(extract_path + 'integrations-core' + sep)
    dest_dir = '{}{}{}'.format(abspath(normpath(options.source)), sep, join('data', 'integrations') + sep)

    if options.integrations:
        options.integrations = abspath(normpath(options.integrations))
        if not options.integrations.endswith(sep):
            options.integrations += sep

    if options.dogweb:
        options.dogweb = abspath(normpath(options.dogweb))
        if not options.dogweb.endswith(sep):
            options.dogweb += sep

    # create data/integrations and other dirs if non existing
    makedirs(dest_dir, exist_ok=True)
    makedirs(dogweb_extract_path, exist_ok=True)
    makedirs(dogweb_extract_path + 'integration' + sep, exist_ok=True)
    makedirs(integrations_extract_path, exist_ok=True)

    # sync from dogweb, download if we don't have it (token required)
    if not options.dogweb:
        if options.token:
            options.dogweb = dogweb_extract_path
            download_github_files(options.token, 'DataDog', 'dogweb', 'prod', options.dogweb + 'integration' + sep, True)
        else:
            print('No Github token.. dogweb retrieval failed')
            exit(1)
    if options.dogweb:
        sync_from_dir(options.dogweb, dest_dir, True)

    # sync from integrations, download if we don't have it (public repo so no token needed)
    # (this takes precedence so will overwrite yaml files)
    if not options.integrations:
        options.integrations = integrations_extract_path
        download_github_files(options.token, 'DataDog', 'integrations-core', 'master', options.integrations)
    sync_from_dir(options.integrations, dest_dir)
    print(options.integrations)
    print (dest_dir)

    #if not options.dogweb:
    #    update_integration_pre_build(options.integrations, dest_dir)

if __name__ == '__main__':
    sync()
