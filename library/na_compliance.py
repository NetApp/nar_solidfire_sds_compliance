#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, NetApp, Inc
"""
Ansible module for checking HCL compliance of SolidFire Enterprise SDS host systems
"""

# For information on running locally and debugging see https://docs.ansible.com/ansible/latest/dev_guide/developing_modules_general.html#exercising-your-module-code

# TODO: Create proper ansible module documentation with ANSIBLE_METADATA, DOCUMENTATION, EXAMPLES, RETURN

from ansible.module_utils.basic import AnsibleModule
import jmespath
import logging
import os
import traceback
import yaml

class ComplianceException(Exception):
    """Base exception for errors encountered during checks"""

    def __init__(self, message, inner_exception=None):
        super(ComplianceException, self).__init__(message)
        self.inner_exception = inner_exception

def load_yaml(filename):
    """Safely load a YAML/JSON file from disk"""

    if not os.path.exists(filename):
        raise ComplianceException("File does not exist: {}".format(filename))
    with open(filename, "r") as fp:
        try:
            data = yaml.safe_load(fp)
        except yaml.YAMLError as e:
            raise ComplianceException("Error loading yaml file: {}".format(e), e)
    return data

def compare_cpu(cpu_file, facts):
    """Compare CPU facts from ansible_facts to the supported list of processors"""

    actual = {"processor":facts["processor"][2],
              "processor_count":facts["processor_count"],
              "processor_cores":facts["processor_cores"],
              "processor_nproc":facts["processor_nproc"]}
    report = dict()
    report["Processor"] = {}
    report["Processor"]["expected"] = {}
    report["Processor"]["actual"] = actual
    report["Processor"]["compliant"] = False
    match = False

    content = load_yaml(cpu_file)
    for expected in content["supported_cpus"]:
        match = (expected["processor"] in actual["processor"] and
                 expected["processor_count"] == actual["processor_count"] and
                 expected["processor_cores"] == actual["processor_cores"] and
                 expected["processor_nproc"] == actual["processor_nproc"])
        if match:
            report["Processor"]["compliant"] = True
            report["Processor"]["expected"] = expected
            break
    return match, report

def compare_facts(constraints, facts):
    """Compare the constraints to the facts from a system and determine compliance"""

    report = dict()

    # descend a level if necessary...
    if "ansible_facts" in facts:
        facts = facts["ansible_facts"]

    # Each entry in the constraints.rules is a high level constraint composed of one or more components
    for constraint_name in constraints:
        logging.info("Checking constraint %s", constraint_name)
        constraint = constraints[constraint_name]
        if "components" not in constraint:
            continue
        report[constraint_name] = {}
        report[constraint_name]["expected"] = constraint["displayName"]
        report[constraint_name]["compliant"] = True
        report[constraint_name]["components"] = {}
        # Components key in each constraint has a list of components to check for this constraint, all of which must be true
        for component_name in constraint["components"]:
            logging.info("Checking component %s", component_name)
            report[constraint_name]["components"][component_name] = {}

            # Read all of the keys for this component
            component_args = {}
            for key in constraint["components"][component_name].keys():
                component_args[key] = constraint["components"][component_name][key]

            # Get the actual query. If there is none, skip this component
            query = component_args.pop("query", None)
            if not query:
                continue
            # Get the query for the actual value (for printing to the report)
            actual_query = component_args.pop("actual", None)

            # Attempt to substitute the args into the query string
            try:
                query = query.format(query, **component_args)
            except ValueError:
                pass

            # Add the args to the report
            report[constraint_name]["components"][component_name].update(component_args)

            # Execute the query for compliance
            match = False
            logging.info("Using query for compliance: %s", query)
            try:
                match = jmespath.search(query, facts)
            except jmespath.exceptions.ParseError as e:
                logging.error("Invalid query")
                logging.error(e)
            except jmespath.exceptions.JMESPathTypeError as e:
                logging.error("Error executing query")
                logging.error(e)
            logging.info("Query for compliance result: %s", match)

            # Execute the query to get the actual value and add it to the report
            actual_value = None
            if query:
                logging.info("Using query for actual: %s", actual_query)
                try:
                    actual_value = jmespath.search(actual_query, facts)
                except jmespath.exceptions.ParseError as e:
                    logging.error("Invalid query")
                    logging.error(e)
                except jmespath.exceptions.JMESPathTypeError as e:
                    logging.error("Error executing query")
                    logging.error(e)
                logging.info("Query for actual result: %s", actual_value)
            report[constraint_name]["components"][component_name]["actual"] = actual_value

            if match:
                report[constraint_name]["components"][component_name]["compliant"] = True
            else:
                report[constraint_name]["components"][component_name]["compliant"] = False
                # Mark parent constraint non-compliant
                report[constraint_name]["compliant"] = False

    compliant = True
    for constraint_name in report:
        if not report[constraint_name]["compliant"]:
            compliant = False
            break
    return compliant, report

def run_module():
    """Entrypoint when run as an ansible module"""
    module_args = dict(
        rule_file=dict(type="str", required=True),
        cpu_file=dict(type="str", required=True),
        facts=dict(type="dict", required=True),
        report_path=dict(type="str", required=True)
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    try:
        # Check report directory exists or create it
        report_dir = os.path.dirname(module.params["report_path"])
        if not os.path.exists(report_dir):
            logging.info("Creating report directory %s", report_dir)
            os.mkdir(report_dir)

        logging.info("Loading compliance rules from file: {}".format(module.params["rule_file"]))
        rules = load_yaml(module.params["rule_file"])

        full_report = dict()
        compliant = False
        fact_product_name = module.params["facts"]["product_name"]

        # Each top level entry in the rules file represents a supported configuration
        # aka a single row in IMT
        for config_name in rules:
            logging.info("Checking source configuration: %s", config_name)

            constraints = rules[config_name]["rules"]
            rule_product_name = constraints["Server Instance"]["components"]["product_name"]["expected"]

            if rule_product_name != fact_product_name:
                continue
            else:
                # We have to check CPU facts separately from other facts due to complexity.
                compliant1, report1 = compare_cpu(module.params["cpu_file"], module.params["facts"])
                compliant2, report2 = compare_facts(constraints, module.params["facts"])
                full_report[config_name] = report1
                full_report[config_name].update(report2)
                compliant = compliant1 and compliant2
                break

        if compliant:
            logging.info("Facts match supported configurations: %s", fact_product_name)
        else:
            logging.warning("No supported configuration for supplied facts: %s", fact_product_name)
            if len(full_report) == 0:
               full_report["compliant"] = False
               full_report["product_name"] = fact_product_name
               full_report["error"] = "This product is not supported for SolidFire eSDS"

        with open(module.params["report_path"], "w") as report_file:
            report_file.write(yaml.dump(full_report))

    except ComplianceException as e:
        logging.error(e)
        msg = "{}\n{}".format(str(e), traceback.format_exc(e))
        module.exit_json(**dict(changed=False, compliant=False, report={"error":msg}))

    except Exception as e: # pylint: disable=broad-except
        logging.error("Unhandled exception:")
        logging.exception(e)
        msg = "{}\n{}".format(str(e), traceback.format_exc(e))
        module.exit_json(**dict(changed=False, compliant=False, report={"error":msg}))

    module.exit_json(**dict(changed=False, compliant=compliant, report=full_report))


if __name__ == "__main__":
    # Uncomment to get more logging when running locally
    # logging.getLogger().setLevel(logging.DEBUG)
    run_module()
