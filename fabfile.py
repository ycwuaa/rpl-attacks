#!/usr/bin/env python
# -*- coding: utf-8 -*-
from lib import *


# ****************************** TASKS ON INDIVIDUAL EXPERIMENT ******************************
@task
def clean(name):
    logging.debug(" > Cleaning folder...")
    with hide(*HIDDEN_ALL):
        with lcd(EXPERIMENT_FOLDER):
            local("rm -rf {}".format(name))


@task
def cooja(name, with_malicious=False):
    logging.info("STARTING COOJA WITH EXPERIMENT '{}'".format(name))
    path = get_path(EXPERIMENT_FOLDER, name)
    get_path(EXPERIMENT_FOLDER, name, 'data')
    with hide(*HIDDEN_ALL):
        with lcd(path):
            local("make cooja-with{}-malicious".format("" if with_malicious else "out"))


@task
def make(name, **kwargs):
    global reuse_bin_path
    logging.info("CREATING EXPERIMENT '{}'".format(name))
    logging.debug(" > Validating parameters...")
    params = validated_parameters(kwargs)
    ext_lib = params.get("ext_lib")
    logging.debug(" > Creating simulation...")
    # create experiment's directories
    path = get_path(EXPERIMENT_FOLDER, name)
    get_path(EXPERIMENT_FOLDER, name, 'motes')
    get_path(EXPERIMENT_FOLDER, name, 'data')
    get_path(EXPERIMENT_FOLDER, name, 'results')
    # select the right malicious mote template and duplicate the simulation file
    copy_files(TEMPLATES_FOLDER, TEMPLATES_FOLDER,
               ('motes/malicious-{}.c'.format(params["mtype"]), 'motes/malicious.c'),
               ('simulation.csc', 'simulation_without_malicious.csc'),
               ('simulation.csc', 'simulation_with_malicious.csc'))
    # create experiment's files from templates
    render_templates(path, **params)
    # then clean the templates folder from previously created files
    remove_files(TEMPLATES_FOLDER,
                 'motes/malicious.c',
                 'simulation_without_malicious.csc',
                 'simulation_with_malicious.csc')
    logging.debug(" > Making motes...")
    path = get_path(EXPERIMENT_FOLDER, name)
    if ext_lib and not exists(ext_lib):
        logging.error("External library does not exist !")
        logging.critical("Make aborded.")
        return
    with hide(*HIDDEN_ALL):
        with lcd(path):
            # for every simulation, root and sensor compilation is the same ;
            #  then, if these were not previously compiled, proceed
            if reuse_bin_path is None:
                local("make motes/root TARGET={}".format(params["target"]))
                local("make motes/sensor TARGET={}".format(params["target"]))
                # after compiling, clean artifacts
                remove_files(path,
                             'contiki-{}.a'.format(params["target"]),
                             'contiki-{}.map'.format(params["target"]),
                             'symbols.c',
                             'symbols.h',
                             'motes/root.c',
                             'motes/sensor.c')
                remove_folder((path, 'obj_{}'.format(params["target"])))
                reuse_bin_path = path
            # otherwise, reuse them by copying the compiled files to the current experiment folder
            else:
                copy_files(reuse_bin_path, path, "motes/root.{}".format(params["target"]),
                           "motes/sensor.{}".format(params["target"]))
    with hide(*HIDDEN_KEEP_STDERR):
        with lcd(path):
            if ext_lib is not None:
                # backup original RPL library and replace it with attack's library
                get_path('.tmp')
                move_folder((CONTIKI_FOLDER, 'core', 'net', 'rpl'), '.tmp')
                copy_folder(ext_lib, (CONTIKI_FOLDER, 'core', 'net', 'rpl'))
            with settings(warn_only=True, abort_exception=Exception):
                try:
                    local("make motes/malicious TARGET={}".format(params["target"]))
                except Exception as e:
                    logging.error(str(e))
            if ext_lib is not None:
                # then, clean temporary files
                remove_folder((CONTIKI_FOLDER, 'core', 'net', 'rpl'))
                move_folder('.tmp/rpl', (CONTIKI_FOLDER, 'core', 'net'))
                remove_folder('.tmp')
            remove_files(path,
                         'contiki-{}.a'.format(params["target"]),
                         'contiki-{}.map'.format(params["target"]),
                         'symbols.c',
                         'symbols.h',
                         'motes/malicious.c')
            remove_folder((path, 'obj_{}'.format(params["target"])))
        with lcd(COOJA_FOLDER):
            local("ant clean")
            local("ant jar")

@task
def run(name):
    logging.info("PROCESSING EXPERIMENT '{}'".format(name))
    path = get_path(EXPERIMENT_FOLDER, name)
    with hide(*HIDDEN_ALL):
        with lcd(path):
            logging.debug(" > Running both simulations (with and without the malicious mote)...")
            local("make run-without-malicious")
            local("make run-with-malicious")
        remove_files(path,
                     'COOJA.log',
                     'COOJA.testlog')


# ****************************** TASKS ON SIMULATION CAMPAIGN ******************************
@task
@expand_file(EXPERIMENT_FOLDER, 'json')
def make_all(exp_file="experiments"):
    global reuse_bin_path
    for name, params in get_experiments(exp_file).items():
        clean(name)
        make(name, **params)


@task
@expand_file(EXPERIMENT_FOLDER, 'json')
def prepare(exp_file='my_simulation'):
    logging.info("CREATING NEW EXPERIMENT CAMPAIGN AT '{}'".format(exp_file))
    copy_files(TEMPLATES_FOLDER, dirname(exp_file), ('experiments.json', exp_file))


@task
@expand_file(EXPERIMENT_FOLDER, 'json')
def run_all(exp_file="experiments"):
    for name in get_experiments(exp_file).keys():
        run(name)


# ****************************** SETUP TASKS FOR CONTIKI AND COOJA ******************************
@task
def config(contiki_folder='~/contiki', experiments_folder='~/Experiments'):
    logging.info("CREATING CONFIGURATION FILE AT '~/.rpl-attacks.conf'")
    with open(expanduser('~/.rpl-attacks.conf'), 'w') as f:
        f.write('[RPL Attacks Framework Configuration]\n')
        f.write('contiki_folder = {}\n'.format(contiki_folder))
        f.write('experiments_folder = {}\n'.format(experiments_folder))


@task
def test():
    setup()
    make("test-simulation")
    with lcd(FRAMEWORK_FOLDER):
        local("python -m unittest tests")


@task
def setup():
    # Install
    cooja_addons_installed = False
    try:
        with open('.cooja_addons_installed') as f:
            f.read()
        logging.info("COOJA ADD-ONS ALREADY INSTALLED")
        cooja_addons_installed = True
    except IOError:
        with open('.cooja_addons_installed', 'w') as f:
            f.write("")
    if not cooja_addons_installed:
        logging.info("INSTALLING COOJA ADD-ONS")
        with hide(*HIDDEN_ALL):
            modify_cooja(COOJA_FOLDER)
            update_cooja_build(COOJA_FOLDER)
            update_cooja_user_properties()
            visualizer = join(COOJA_FOLDER, 'apps', 'visualizer_screenshot')
            if not exists(visualizer):
                copy_folder('src/visualizer_screenshot', visualizer)
            with lcd(COOJA_FOLDER):
                with settings(warn_only=True):
                    local("ant clean")
                local("ant jar")
    with hide(*HIDDEN_ALL):
        msp430_version_output = local('msp430-gcc --version', capture=True)
    if 'msp430-gcc (GCC) 4.7.0 20120322' not in msp430_version_output:
        if input("In order to extend msp430x memory support, it is necessary to upgrade msp430-gcc.\n"
                 "Would you like to upgrade it now ? (yes|no) [default: no] ") == "yes":
            logging.info("UPGRADING msp430-gcc FROM VERSION 4.6.3 TO 4.7.0")
            with lcd('src/'):
                logging.warning(" > Upgrade now starts, this may take up to 30 minutes...")
                sudo('./upgrade-msp430.sh')
                sudo('rm -r tmp/')
                local('export PATH=/usr/local/msp430/bin:$PATH')
                register_new_path_in_profile()
        else:
            logging.info("UPGRADE OF LIBRARY msp430-gcc ABORTED")
            logging.warning("You may experience problems of mote memory size at compilation")
    else:
        logging.info("LIBRARY msp430-gcc IS UP-TO-DATE (4.7.0)")


# **************************************** MAGIC TASK ****************************************
@task
def rip_my_slip():
    # TODO: prepare 'rpl-attacks' campaign, make all its experiments then run them
    print("yeah, man !")
