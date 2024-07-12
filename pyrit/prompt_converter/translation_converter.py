import json
import logging
import uuid
import pathlib

from pyrit.common.path import DATASETS_PATH
from pyrit.exceptions.exception_classes import (
    InvalidJsonException,
    pyrit_json_retry,
    remove_markdown_json,
)
from pyrit.models import PromptDataType, PromptRequestPiece, PromptRequestResponse, PromptTemplate
from pyrit.prompt_converter import PromptConverter, ConverterResult
from pyrit.prompt_target import PromptChatTarget

logger = logging.getLogger(__name__)


class TranslationConverter(PromptConverter):
    def __init__(self, *, converter_target: PromptChatTarget, language: str, prompt_template: PromptTemplate = None):
        """
        Initializes a TranslationConverter object.

        Args:
            converter_target (PromptChatTarget): The target chat support for the conversion which will translate
            language (str): The language for the conversion. E.g. Spanish, French, leetspeak, etc.
            prompt_template (PromptTemplate, optional): The prompt template for the conversion.

        Raises:
            ValueError: If the language is not provided.
        """
        self.converter_target = converter_target

        # set to default strategy if not provided
        prompt_template = (
            prompt_template
            if prompt_template
            else PromptTemplate.from_yaml_file(
                pathlib.Path(DATASETS_PATH) / "prompt_converters" / "translation_converter.yaml"
            )
        )

        if not language:
            raise ValueError("Language must be provided for translation conversion")

        self.language = language.lower()

        self.system_prompt = prompt_template.apply_custom_metaprompt_parameters(languages=language)

    async def convert_async(self, *, prompt: str, input_type: PromptDataType = "text") -> ConverterResult:
        """
        Generates variations of the input prompt using the converter target.
        Parameters:
            prompt (str): prompt to convert
        Return:
            (ConverterResult): result generated by the converter target
        """

        conversation_id = str(uuid.uuid4())

        self.converter_target.set_system_prompt(
            system_prompt=self.system_prompt,
            conversation_id=conversation_id,
            orchestrator_identifier=None,
        )

        if not self.input_supported(input_type):
            raise ValueError("Input type not supported")

        request = PromptRequestResponse(
            [
                PromptRequestPiece(
                    role="user",
                    original_value=prompt,
                    converted_value=prompt,
                    conversation_id=conversation_id,
                    sequence=1,
                    prompt_target_identifier=self.converter_target.get_identifier(),
                    original_value_data_type=input_type,
                    converted_value_data_type=input_type,
                    converter_identifiers=[self.get_identifier()],
                )
            ]
        )

        response = await self.send_variation_prompt_async(request)
        translation = None
        for key in response.keys():
            if key.lower() == self.language:
                translation = response[key]

        return ConverterResult(output_text=translation, output_type="text")

    @pyrit_json_retry
    async def send_variation_prompt_async(self, request):
        response = await self.converter_target.send_prompt_async(prompt_request=request)

        response_msg = response.request_pieces[0].converted_value
        response_msg = remove_markdown_json(response_msg)

        try:
            llm_response: dict[str, str] = json.loads(response_msg)
            if "output" not in llm_response:
                raise InvalidJsonException(message=f"Invalid JSON encountered; missing 'output' key: {response_msg}")
            return llm_response["output"]

        except json.JSONDecodeError:
            raise InvalidJsonException(message=f"Invalid JSON encountered: {response_msg}")

    def input_supported(self, input_type: PromptDataType) -> bool:
        return input_type == "text"
