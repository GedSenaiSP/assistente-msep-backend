import logging
import multiprocessing
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    PaginatedPipelineOptions,
    AcceleratorOptions,
    AcceleratorDevice
)
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
    WordFormatOption,
    PowerpointFormatOption,
    ExcelFormatOption
)
from docling.pipeline.simple_pipeline import SimplePipeline

_log = logging.getLogger(__name__)

def setup_optimized_converter() -> DocumentConverter:
    """
    Configura e retorna um DocumentConverter com pipelines otimizados
    separados para PDF e documentos do Office.
    """

    # --- 1. Otimizações de PDF (Pipeline de IA) ---
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = True
    pdf_options.do_table_structure = True
    pdf_options.table_structure_options.do_cell_matching = True
    pdf_options.do_code_enrichment = True
    pdf_options.do_picture_classification = False

    num_cores = multiprocessing.cpu_count()
    pdf_options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.AUTO,
        num_threads=num_cores
    )
    
    # --- 2. Otimizações do Office (Pipeline Simples) ---
    office_options = PaginatedPipelineOptions()
    office_options.generate_page_images = True
    office_options.images_scale = 1.5

    # --- 3. Configuração do Conversor Unificado ---
    _log.info(f"Configurando DocumentConverter com {num_cores} threads.")
    
    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pdf_options
            ),
            InputFormat.DOCX: WordFormatOption(
                pipeline_options=office_options,
                pipeline_cls=SimplePipeline
            ),
            InputFormat.PPTX: PowerpointFormatOption(
                pipeline_options=office_options,
                pipeline_cls=SimplePipeline
            ),
            InputFormat.XLSX: ExcelFormatOption(
                pipeline_options=office_options,
                pipeline_cls=SimplePipeline
            )
        }
    )
    return doc_converter
