

from typing import List, Dict, Any
import re
import json
from groq import Groq


class QueryProcessor:
    """
    Process queries and generate responses
    with proper citations and conversation context
    """

    def __init__(self, grok_api_key: str):

        self.grok_api_key = grok_api_key

        self.client = Groq(
            api_key=grok_api_key
        )

    def analyze_query(
        self,
        query: str,
        conversation_context: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        query_lower = query.lower()

        # =========================
        # CONVERSATION CONTEXT
        # =========================

        current_drug = None

        if conversation_context:

            for exchange in reversed(conversation_context):

                if exchange.get('detected_drug'):
                    current_drug = exchange['detected_drug']
                    break

        # =========================
        # DRUG KEYWORDS
        # =========================

        drug_keywords = {
            'orencia': 'orencia',
            'simponi': 'simponi',
            'aria': 'aria',
            'humira': 'humira',
            'enbrel': 'enbrel',
            'remicade': 'remicade',
            'keytruda': 'keytruda',
            'alora': 'alora_pi',
            'augtyro': 'augtyro',
            'blujepa': 'blujepa',
            'cinbinqo': 'cinbinqo',
            'dalvance': 'dalvance_pi',
            'herceptin': 'herceptin',
            'ibuprofen': 'ibuprofen',
            'jakafi': 'jakafi',
            'methadone': 'methadone',
            'olumiant': 'olumiant',
            'opzelura': 'opzelura-prescribing-infor',
            'prilosec': 'prilosec',
            'rinvoq': 'rinvoq_pi',
            'sotyktu': 'sotyktu',
            'stelara': 'stelara',
            'xeljanz': 'xeljanz'
        }

        mentioned_drugs = []

        pdf_filter = current_drug

        for drug, filter_term in drug_keywords.items():

            if drug in query_lower:

                mentioned_drugs.append(drug)

                pdf_filter = filter_term

        # =========================
        # MEDICAL KEYWORDS
        # =========================

        medical_keywords = {
            'dose',
            'dosage',
            'side effect',
            'adverse',
            'warning',
            'contraindication',
            'interaction',
            'administration',
            'treatment',
            'safety',
            'efficacy',
            'pharmacokinetics',
            'indication'
        }

        is_medical_query = any(
            keyword in query_lower
            for keyword in medical_keywords
        )

        visual_keywords = {
            'graph',
            'chart',
            'diagram',
            'figure',
            'image',
            'picture',
            'visual'
        }

        is_visual_query = any(
            keyword in query_lower
            for keyword in visual_keywords
        )

        is_follow_up = self._is_follow_up_query(
            query,
            conversation_context
        )

        return {
            "mentioned_drugs": mentioned_drugs,
            "is_medical_query": is_medical_query,
            "is_visual_query": is_visual_query,
            "is_fda_specific": is_medical_query,
            "pdf_filter": pdf_filter,
            "prefer_medical": is_medical_query,
            "prefer_visual": is_visual_query,
            "is_follow_up": is_follow_up,
            "current_drug": current_drug
        }

    def _is_follow_up_query(
        self,
        query: str,
        conversation_context: List[Dict[str, Any]]
    ) -> bool:

        if not conversation_context:
            return False

        follow_up_patterns = [
            r'what about',
            r'how about',
            r'what are (?:its|their)',
            r'what is (?:its|their)',
            r'what does (?:it|they)',
            r'can you tell me more',
            r'and (?:its|their)',
            r'also',
            r'too'
        ]

        query_lower = query.lower()

        for pattern in follow_up_patterns:

            if re.search(pattern, query_lower):
                return True

        return False

    def format_retrieved_info(
        self,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> str:

        if not retrieved_chunks:
            return "No relevant information found."

        formatted_info = (
            "RETRIEVED INFORMATION "
            "WITH SOURCE CITATIONS:\n\n"
        )

        for i, chunk in enumerate(retrieved_chunks, 1):

            citation_parts = [
                f"Source: {chunk.get('pdf_name', 'Unknown PDF')}"
            ]

            if (
                chunk.get('section')
                and chunk['section']
                not in [
                    "TABULAR_DATA",
                    "VISUAL_DATA",
                    "TABULAR_DATA_ROW"
                ]
            ):

                citation_parts.append(
                    f"Section: {chunk['section']}"
                )

            page_info = self._get_page_info(chunk)

            if page_info:
                citation_parts.append(
                    f"Page: {page_info}"
                )

            citation = ", ".join(citation_parts)

            formatted_info += (
                f"{i}. {citation}\n"
                f"Content: {chunk['chunk_text']}\n\n"
            )

        return formatted_info

    def _get_page_info(
        self,
        chunk: Dict[str, Any]
    ) -> str:

        if chunk.get('pdf_page_number'):
            return str(chunk['pdf_page_number'])

        elif (
            chunk.get('pdf_page_start')
            and chunk.get('pdf_page_end')
        ):

            if (
                chunk['pdf_page_start']
                == chunk['pdf_page_end']
            ):

                return str(chunk['pdf_page_start'])

            else:

                return (
                    f"{chunk['pdf_page_start']}"
                    f"-{chunk['pdf_page_end']}"
                )

        return "Unknown"

    def generate_response(
        self,
        user_query: str,
        retrieved_info: str,
        conversation_context: List[Dict[str, Any]] = None
    ) -> str:

        context_prompt = ""

        if conversation_context:

            context_prompt = (
                "\nCONVERSATION CONTEXT:\n"
            )

            for exchange in conversation_context[-5:]:

                context_prompt += (
                    f"User: "
                    f"{exchange['user_query']}\n"
                )

                context_prompt += (
                    f"Assistant: "
                    f"{exchange['assistant_response'][:200]}"
                    f"...\n\n"
                )

        prompt = f"""
You are a helpful medical information assistant.

Use ONLY the provided information.

USER QUESTION:
{user_query}

{context_prompt}

RETRIEVED INFORMATION:
{retrieved_info}

RULES:
- Answer clearly
- Be conversational
- Do not hallucinate
- Use only retrieved info
- Mention source document and page
- Do not use markdown headings

RESPONSE:
"""

        try:

            response = self.client.chat.completions.create(

                model="llama-3.1-8b-instant",

                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],

                temperature=0.7,
                max_tokens=1024
            )

            response_text = (
                response.choices[0]
                .message.content
            )

            response_text = (
                response_text
                .replace("**", "")
                .replace("*", "")
            )

            return response_text

        except Exception as e:

            return (
                "I apologize, but I encountered "
                f"an error: {str(e)}"
            )