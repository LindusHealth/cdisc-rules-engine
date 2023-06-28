import asyncio
import json
import logging
import os
import pickle
from datetime import datetime
from multiprocessing import freeze_support
from typing import Iterable, Tuple

import click
from pathlib import Path
from cdisc_rules_engine.config import config
from cdisc_rules_engine.constants.define_xml_constants import DEFINE_XML_FILE_NAME
from cdisc_rules_engine.enums.default_file_paths import DefaultFilePaths
from cdisc_rules_engine.enums.progress_parameter_options import ProgressParameterOptions
from cdisc_rules_engine.enums.report_types import ReportTypes
from cdisc_rules_engine.models.validation_args import Validation_args
from cdisc_rules_engine.models.test_args import TestArgs
from scripts.run_validation import run_validation
from scripts.test_rule import test as test_rule
from cdisc_rules_engine.services.cache.cache_populator_service import CachePopulator
from cdisc_rules_engine.services.cache.cache_service_factory import CacheServiceFactory
from cdisc_rules_engine.services.cdisc_library_service import CDISCLibraryService
from cdisc_rules_engine.utilities.utils import (
    generate_report_filename,
    get_rules_cache_key,
)
from scripts.list_dataset_metadata_handler import list_dataset_metadata_handler
from version import __version__


def valid_data_file(file_name: str, data_format: str):
    fn = os.path.basename(file_name)
    return fn.lower() != DEFINE_XML_FILE_NAME and fn.lower().endswith(
        f".{data_format.lower()}"
    )


@click.group()
def cli():
    pass


@click.command()
@click.option(
    "-ca",
    "--cache",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)
@click.option(
    "-ps",
    "--pool-size",
    default=10,
    type=int,
    help="Number of parallel processes for validation",
)
@click.option(
    "-d",
    "--data",
    required=False,
    help="Path to directory containing data files",
)
@click.option(
    "-dp",
    "--dataset-path",
    required=False,
    multiple=True,
    help="Absolute path to dataset file",
)
@click.option("-dxp", "--define-xml-path", default="test", help="Path to Define-XML")
@click.option(
    "-l",
    "--log-level",
    default="disabled",
    type=click.Choice(["info", "debug", "error", "critical", "disabled", "warn"]),
    help="Sets log level for engine logs, logs are disabled by default",
)
@click.option(
    "-rt",
    "--report-template",
    default=DefaultFilePaths.EXCEL_TEMPLATE_FILE.value,
    help="File path of report template to use for excel output",
)
@click.option(
    "-s", "--standard", required=True, help="CDISC standard to validate against"
)
@click.option(
    "-v", "--version", required=True, help="Standard version to validate against"
)
@click.option(
    "-ct",
    "--controlled-terminology-package",
    multiple=True,
    help=(
        "Controlled terminology package to validate against, "
        "can provide more than one"
    ),
)
@click.option(
    "-o",
    "--output",
    default=generate_report_filename(datetime.now().isoformat()),
    help="Report output file destination",
)
@click.option(
    "-of",
    "--output-format",
    multiple=True,
    default=[ReportTypes.XLSX.value],
    type=click.Choice(ReportTypes.values(), case_sensitive=False),
    help="Output file format",
)
@click.option(
    "-rr",
    "--raw-report",
    default=False,
    show_default=True,
    is_flag=True,
    help="Report in a raw format as it is generated by the engine. "
    "This flag must be used only with --output-format JSON.",
)
@click.option(
    "-dv",
    "--define-version",
    help="Define-XML version used for validation",
)
@click.option(
    "-df",
    "--data-format",
    help="Format in which data files are presented. Defaults to XPT.",
    type=click.Choice(["xpt"], case_sensitive=False),
    default="xpt",
    required=True,
)
@click.option("--whodrug", help="Path to directory with WHODrug dictionary files")
@click.option("--meddra", help="Path to directory with MedDRA dictionary files")
@click.option("--rules", "-r", multiple=True)
@click.option(
    "-p",
    "--progress",
    default=ProgressParameterOptions.BAR.value,
    type=click.Choice(ProgressParameterOptions.values()),
    help=(
        "Defines how to display the validation progress. "
        'By default a progress bar like "[████████████████████████████--------]   78%"'
        "is printed."
    ),
)
@click.pass_context
def validate(
    ctx,
    cache: str,
    pool_size: int,
    data: str,
    dataset_path: Tuple[str],
    define_xml_path: str,
    log_level: str,
    report_template: str,
    standard: str,
    version: str,
    controlled_terminology_package: Tuple[str],
    output: str,
    output_format: Tuple[str],
    raw_report: bool,
    define_version: str,
    data_format: str,
    whodrug: str,
    meddra: str,
    rules: Tuple[str],
    progress: str,
):
    """
    Validate data using CDISC Rules Engine

    Example:

    python core.py -s SDTM -v 3.4 -d /path/to/datasets
    """

    # Validate conditional options
    logger = logging.getLogger("validator")


    if raw_report is True:
        if not (len(output_format) == 1 and output_format[0] == ReportTypes.JSON.value):
            logger.error(
                "Flag --raw-report can be used only when --output-format is JSON"
            )
            ctx.exit()

    cache_path: str = os.path.join(os.path.dirname(__file__), cache)

    if data:
        if dataset_path:
            logger.error(
                "Argument --dataset-path cannot be used together with argument --data"
            )
            ctx.exit()
        dataset_paths: Iterable[str] = [
            str(Path(data).joinpath(fn))
            for fn in os.listdir(data)
            if valid_data_file(fn, data_format)
        ]
    elif dataset_path:
        if data:
            logger.error(
                "Argument --dataset-path cannot be used together with argument --data"
            )
            ctx.exit()
        dataset_paths: Iterable[str] = [
            dp for dp in dataset_path if valid_data_file(dp, data_format)
        ]
    else:
        logger.error(
            "You must pass one of the following arguments: --dataset-path, --data"
        )
        # no need to define dataset_paths here, the program execution will stop
        ctx.exit()

    run_validation(
        Validation_args(
            cache_path,
            pool_size,
            dataset_paths,
            log_level,
            report_template,
            standard,
            version,
            set(controlled_terminology_package),  # avoiding duplicates
            output,
            set(output_format),  # avoiding duplicates
            raw_report,
            define_version,
            data_format.lower(),
            whodrug,
            meddra,
            rules,
            progress,
            define_xml_path
        )
    )


@click.command()
@click.option(
    "-c",
    "--cache_path",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)
@click.option(
    "--apikey",
    envvar="CDISC_LIBRARY_API_KEY",
    help=(
        "CDISC Library api key. "
        "Can be provided in the environment "
        "variable CDISC_LIBRARY_API_KEY"
    ),
    required=True,
)
@click.pass_context
def update_cache(ctx: click.Context, cache_path: str, apikey: str):
    cache = CacheServiceFactory(config).get_cache_service()
    library_service = CDISCLibraryService(apikey, cache)
    cache_populator = CachePopulator(cache, library_service)
    cache = asyncio.run(cache_populator.load_cache_data())
    cache_populator.save_rules_locally(
        os.path.join(cache_path, DefaultFilePaths.RULES_CACHE_FILE.value)
    )
    cache_populator.save_ct_packages_locally(f"{cache_path}")
    cache_populator.save_standards_metadata_locally(
        os.path.join(cache_path, DefaultFilePaths.STANDARD_DETAILS_CACHE_FILE.value)
    )
    cache_populator.save_standards_models_locally(
        os.path.join(cache_path, DefaultFilePaths.STANDARD_MODELS_CACHE_FILE.value)
    )
    cache_populator.save_variable_codelist_maps_locally(
        os.path.join(cache_path, DefaultFilePaths.VARIABLE_CODELIST_CACHE_FILE.value)
    )
    cache_populator.save_variables_metadata_locally(
        os.path.join(cache_path, DefaultFilePaths.VARIABLE_METADATA_CACHE_FILE.value)
    )


@click.command()
@click.option(
    "-c",
    "--cache_path",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)

@click.option(
    "-s", "--standard", required=False, help="CDISC standard to get rules for"
)
@click.option(
    "-v", "--version", required=False, help="Standard version to get rules for"
)
@click.pass_context
def list_rules(ctx: click.Context, cache_path: str, standard: str, version: str):
    # Load all rules
    rules_file = DefaultFilePaths.RULES_CACHE_FILE.value
    with open(os.path.join(cache_path, rules_file), "rb") as f:
        rules_data = pickle.load(f)
    if standard and version:
        key_prefix = get_rules_cache_key(standard, version.replace(".", "-"))
        rules = [rule for key, rule in rules_data.items() if key.startswith(key_prefix)]
    else:
        # Print all rules
        rules = list(rules_data.values())
    print(json.dumps(rules, indent=4))


@click.command()
@click.option(
    "-c",
    "--cache_path",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)
@click.option(
    "-dp",
    "--dataset-path",
    required=True,
    help="Absolute path to dataset file",
)
@click.option("-dxp", "--define-xml-path", required=False, help="Path to Define-XML")
@click.option(
    "-r",
    "--rule",
    required=True,
    help="Absolute path to rule file",
)
@click.option("--whodrug", help="Path to directory with WHODrug dictionary files")
@click.option("--meddra", help="Path to directory with MedDRA dictionary files")
@click.option(
    "-s", "--standard", required=False, help="CDISC standard to get rules for"
)
@click.option(
    "-v", "--version", required=False, help="Standard version to get rules for"
)
@click.option(
    "-ct",
    "--controlled-terminology-package",
    multiple=True,
    help=(
        "Controlled terminology package to validate against, "
        "can provide more than one"
    ),
)
@click.option(
    "-dv",
    "--define-version",
    help="Define-XML version used for validation",
)
@click.pass_context
def test(
    ctx,
    cache_path: str,
    dataset_path: Tuple[str],
    define_xml_path: str,
    standard: str,
    version: str,
    controlled_terminology_package: Tuple[str],
    define_version: str,
    whodrug: str,
    meddra: str,
    rule: str,
):
    args = TestArgs(
        cache_path,
        dataset_path,
        rule,
        standard,
        version,
        whodrug,
        meddra,
        controlled_terminology_package,
        define_version,
        define_xml_path,
    )
    test_rule(args)


@click.command()
@click.option(
    "-c",
    "--cache_path",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)
@click.pass_context
def list_rule_sets(ctx: click.Context, cache_path: str):
    # Load all rules
    rules_file = DefaultFilePaths.RULES_CACHE_FILE.value
    with open(os.path.join(cache_path, rules_file), "rb") as f:
        rules_data = pickle.load(f)
    rule_sets = set()
    for rule in rules_data.keys():
        standard, version = rule.split("/")[1:3]
        rule_set = f"{standard.upper()}, {version}"
        if rule_set not in rule_sets:
            print(rule_set)
            rule_sets.add(rule_set)


@click.command()
@click.option(
    "-dp",
    "--dataset-path",
    required=True,
    multiple=True,
)
@click.pass_context
def list_dataset_metadata(ctx: click.Context, dataset_path: Tuple[str]):
    """
    Command that lists metadata of given datasets.

    Input:
        core.py list-ds-metadata -dp=path_1 -dp=path_2 -dp=path_3 ...
    Output:
        [
           {
              "domain":"AE",
              "filename":"ae.xpt",
              "full_path":"/Users/Aleksei_Furmenkov/PycharmProjects/cdisc-rules-engine/resources/data/ae.xpt",
              "size":"38000",
              "label":"Adverse Events",
              "modification_date":"2020-08-21T09:14:26"
           },
           {
              "domain":"EX",
              "filename":"ex.xpt",
              "full_path":"/Users/Aleksei_Furmenkov/PycharmProjects/cdisc-rules-engine/resources/data/ex.xpt",
              "size":"78050",
              "label":"Exposure",
              "modification_date":"2021-09-17T09:23:22"
           },
           ...
        ]
    """
    print(json.dumps(list_dataset_metadata_handler(dataset_path), indent=4))


@click.command()
def version():
    print(__version__)


@click.command()
@click.option(
    "-c",
    "--cache_path",
    default=DefaultFilePaths.CACHE.value,
    help="Relative path to cache files containing pre loaded metadata and rules",
)
@click.option(
    "-s",
    "--subsets",
    help="CT package subset type. Ex: sdtmct. Multiple values allowed",
    required=False,
    multiple=True,
)
def list_ct(cache_path: str, subsets: Tuple[str]):
    """
    Command to list the ct packages available in the cache.
    """
    if subsets:
        subsets = set([subset.lower() for subset in subsets])

    for file in os.listdir(cache_path):
        file_prefix = file.split("-")[0]
        if file_prefix.endswith("ct") and (not subsets or file_prefix in subsets):
            print(os.path.splitext(file)[0])


cli.add_command(validate)
cli.add_command(update_cache)
cli.add_command(list_rules)
cli.add_command(list_rule_sets)
cli.add_command(list_dataset_metadata)
cli.add_command(test)
cli.add_command(version)
cli.add_command(list_ct)

if __name__ == "__main__":
    freeze_support()
    cli()
