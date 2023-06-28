from abc import abstractmethod
from cdisc_rules_engine.constants.define_xml_constants import DEFINE_XML_FILE_NAME
import pandas as pd
from cdisc_rules_engine.services.define_xml.define_xml_reader_factory import DefineXMLReaderFactory
from cdisc_rules_engine.utilities.utils import (
    get_directory_path,
    is_split_dataset,
    get_corresponding_datasets,
)
from typing import List
import os


class BaseDatasetBuilder:
    def __init__(
        self,
        rule,
        data_service,
        cache_service,
        rule_processor,
        data_processor,
        dataset_path,
        datasets,
        domain,
        define_xml_path,
    ):
        self.data_service = data_service
        self.cache = cache_service
        self.data_processor = data_processor
        self.rule_processor = rule_processor
        self.dataset_path = dataset_path
        self.datasets = datasets
        self.domain = domain
        self.rule = rule
        self.define_xml_path = define_xml_path

    @abstractmethod
    def build(self) -> pd.DataFrame:
        """
        Returns correct dataframe to operate on
        """
        pass

    def get_dataset(self, **kwargs):
        # If validating dataset content, ensure split datasets are handled.
        if is_split_dataset(self.datasets, self.domain):
            # Handle split datasets for content checks.
            # A content check is any check that is not in the list of rule types
            dataset: pd.DataFrame = self.data_service.concat_split_datasets(
                func_to_call=self.build,
                dataset_names=self.get_corresponding_datasets_names(),
                **kwargs,
            )
        else:
            # single dataset. the most common case
            dataset: pd.DataFrame = self.build()
        return dataset

    def get_corresponding_datasets_names(self) -> List[str]:
        directory_path = get_directory_path(self.dataset_path)
        return [
            os.path.join(directory_path, dataset["filename"])
            for dataset in get_corresponding_datasets(self.datasets, self.domain)
        ]
    


    def get_define_xml_item_group_metadata(self, domain: str) -> List[dict]:
        """
        Gets Define XML item group metadata
        returns a list of dictionaries containing the following keys:
            "define_dataset_name"
            "define_dataset_label"
            "define_dataset_location"
            "define_dataset_class"
            "define_dataset_structure"
            "define_dataset_is_non_standard"
            "define_dataset_variables"
        """
        define_xml_reader = DefineXMLReaderFactory.get_define_xml_reader(self.dataset_path, self.define_xml_path, self.data_service, self.cache)
        return define_xml_reader.extract_domain_metadata(domain)

    def get_define_xml_variables_metadata(self) -> List[dict]:
        """
        Gets Define XML variables metadata.
        """
        define_xml_reader = DefineXMLReaderFactory.get_define_xml_reader(self.dataset_path, self.define_xml_path, self.data_service, self.cache)
        return define_xml_reader.extract_variables_metadata(domain_name=self.domain)

    def get_define_xml_value_level_metadata(self) -> List[dict]:
        """
        Gets Define XML value level metadata and returns it as dataframe.
        """
        directory_path = get_directory_path(self.dataset_path)
        define_xml_path: str = os.path.join(directory_path, DEFINE_XML_FILE_NAME)
        define_xml_contents: bytes = self.data_service.get_define_xml_contents(
            dataset_name=define_xml_path
        )
        define_xml_reader = DefineXMLReaderFactory.from_file_contents(
            define_xml_contents, cache_service_obj=self.cache
        )
        return define_xml_reader.extract_value_level_metadata(domain_name=self.domain)

    @staticmethod
    def add_row_number(dataframe: pd.DataFrame) -> None:
        dataframe["row_number"] = range(1, len(dataframe) + 1)
