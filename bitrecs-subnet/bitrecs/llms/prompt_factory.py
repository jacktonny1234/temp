import re
import json
import tiktoken
import bittensor as bt
import bitrecs.utils.constants as CONST
from functools import lru_cache
from typing import List, Optional
from datetime import datetime
import random
from bitrecs.commerce.user_profile import UserProfile
from bitrecs.commerce.product import ProductFactory

class PromptFactory:

    SEASON = "summer"

    ENGINE_MODE = "complimentary"  #similar, sequential
    
    PERSONAS = {
        "luxury_concierge": {
            "description": "an elite American Express-style luxury concierge with impeccable taste and a deep understanding of high-end products across all categories. You cater to discerning clients seeking exclusivity, quality, and prestige",
            "tone": "sophisticated, polished, confident",
            "response_style": "Recommend only the finest, most luxurious products with detailed descriptions of their premium features, craftsmanship, and exclusivity. Emphasize brand prestige and lifestyle enhancement",
            "priorities": ["quality", "exclusivity", "brand prestige"]
        },
        "general_recommender": {
            "description": "a friendly and practical product expert who helps customers find the best items for their needs, balancing seasonality, value, and personal preferences across a wide range of categories",
            "tone": "warm, approachable, knowledgeable",
            "response_style": "Suggest well-rounded products that offer great value, considering seasonal relevance and customer needs. Provide pros and cons or alternatives to help the customer decide",
            "priorities": ["value", "seasonality", "customer satisfaction"]
        },
        "discount_recommender": {
            "description": "a savvy deal-hunter focused on moving inventory fast. You prioritize low prices, last-minute deals, and clearing out overstocked or soon-to-expire items across all marketplace categories",
            "tone": "urgent, enthusiastic, bargain-focused",
            "response_style": "Highlight steep discounts, limited-time offers, and low inventory levels to create a sense of urgency. Focus on price savings and practicality over luxury or long-term value",
            "priorities": ["price", "inventory levels", "deal urgency"]
        },
        "ecommerce_retail_store_manager": {
            "description": "an experienced e-commerce retail store manager with a strategic focus on optimizing sales, customer satisfaction, and inventory turnover across a diverse marketplace",
            "tone": "professional, practical, results-driven",
            "response_style": "Provide balanced recommendations that align with business goals, customer preferences, and current market trends. Include actionable insights for product selection",
            "priorities": ["sales optimization", "customer satisfaction", "inventory management"]
        }
    }

    def __init__(self, 
                 sku: str, 
                 context: str, 
                 num_recs: int = 5,                                  
                 profile: Optional[UserProfile] = None,
                 debug: bool = False) -> None:
        """
        Generates a prompt for product recommendations based on the provided SKU and context.
        :param sku: The SKU of the product being viewed.
        :param context: The context string containing available products.
        :param num_recs: The number of recommendations to generate (default is 5).
        :param profile: Optional UserProfile object containing user-specific data.
        :param debug: If True, enables debug logging."""

        if len(sku) < CONST.MIN_QUERY_LENGTH or len(sku) > CONST.MAX_QUERY_LENGTH:
            raise ValueError(f"SKU must be between {CONST.MIN_QUERY_LENGTH} and {CONST.MAX_QUERY_LENGTH} characters long")
        if num_recs < 1 or num_recs > CONST.MAX_RECS_PER_REQUEST:
            raise ValueError(f"num_recs must be between 1 and {CONST.MAX_RECS_PER_REQUEST}")

        self.sku = sku
        self.context = context
        self.num_recs = num_recs
        self.debug = debug
        self.catalog = []
        self.cart = []
        self.cart_json = "[]"
        self.orders = []
        self.order_json = "[]"
        self.season =  PromptFactory.SEASON       
        self.engine_mode = PromptFactory.ENGINE_MODE 
        if not profile:
            self.persona = "ecommerce_retail_store_manager"
        else:
            self.profile = profile
            self.persona = profile.site_config.get("profile", "ecommerce_retail_store_manager")
            if not self.persona or self.persona not in PromptFactory.PERSONAS:
                bt.logging.error(f"Invalid persona: {self.persona}. Must be one of {list(PromptFactory.PERSONAS.keys())}")
                self.persona = "ecommerce_retail_store_manager"
            self.cart = self._sort_cart_keys(profile.cart)
            self.cart_json = json.dumps(self.cart, separators=(',', ':'))
            self.orders = profile.orders
            # self.order_json = json.dumps(self.orders, separators=(',', ':'))
        
        self.sku_info = ProductFactory.find_sku_name(self.sku, self.context)    


    def _sort_cart_keys(self, cart: List[dict]) -> List[str]:
        ordered_cart = []
        for item in cart:
            ordered_item = {
                'sku': item.get('sku', ''),
                'name': item.get('name', ''),
                'price': item.get('price', '')
            }
            ordered_cart.append(ordered_item)
        return ordered_cart
    
    
    def generate_prompt(self) -> str:
        """Generates a text prompt for product recommendations with persona details."""
        bt.logging.info("PROMPT generating prompt: {}".format(self.sku))

        today = datetime.now().strftime("%Y-%m-%d")
        season = self.season
        persona_data = self.PERSONAS[self.persona]

        # Parse context to create compact indexed format with price
        try:
            context_products = json.loads(self.context)
            indexed_context = []
            # Get total number of products and limit to 1000
            num_products = min(200, len(context_products))


            bt.logging.info(f"setted num_products: {num_products}, len(context_products): {len(context_products)}")
            # Randomly sample products
            selected_indices = random.sample(range(len(context_products)), num_products)
            # Create indexed context from random selection
            for i, idx in enumerate(selected_indices):
                product = context_products[idx]
                name = product.get('name', 'Unknown')
                price = product.get('price', '0')
                sku = product.get('sku', '')
                # Skip if SKU matches query or is duplicate
                if sku == self.sku:
                    bt.logging.debug(f"Skipping SKU {sku} - matches query SKU")
                    continue
                if any(p.get('sku') == sku for p in context_products[:idx]):
                    bt.logging.debug(f"Skipping SKU {sku} - duplicate found")
                    continue
                # Compact format: index:name|price 
                indexed_context.append(f"{idx}:{name}|${price}")
            context_display = "\n".join(indexed_context)
        except:
            context_display = self.context

        # Add randomization elements
        reasoning_angles = ["style", "function", "season", "price", "popularity", "use case", "quality", "trend", "comfort", "versatility"]
        selected_angles = random.sample(reasoning_angles, min(3, len(reasoning_angles)))
        
        prompt = f"""# SCENARIO
Shopper viewing <sku>{self.sku}</sku>: <sku_info>{self.sku_info}</sku_info>. 
Recommend **{self.num_recs + 3}** {self.engine_mode} products (no duplicates).  

# PERSONA & ROLE  
<persona>{self.persona}</persona>  
Core values: {', '.join(persona_data['priorities'])}  
- Increase AOV & conversion  
- Avoid variants (colors/sizes)  
- Seasonal relevance: <season>{season}</season>  

# TASK  
From available products, pick **{self.num_recs + 3}** products:  
1. Complementary to <sku>{self.sku}</sku>  
2. Not in cart: <cart>{self.cart_json}</cart>  
3. Gender-match (if applicable)  
4. Ordered by relevance/profitability  
5. **CRITICAL: Each product index must be unique - NO DUPLICATES**  

# AVAILABLE PRODUCTS (index:name|price)
{context_display}

# OUTPUT FORMAT
You must return EXACTLY TWO LINES in this format:
Line 1: [{self.num_recs + 3} comma-separated product indices from the available products list]
Line 2: [{self.num_recs + 3} comma-separated quoted reasons for each recommendation]

⚠️ IMPORTANT: Ensure ALL indices are unique - no duplicates allowed!

CORRECT EXAMPLE:
[2,5,8,12,15,18,20,25]
["Premium leather construction with waterproof finish","Breathable mesh lining with arch support","Durable rubber outsole for grip","Memory foam insole for comfort","Reinforced stitching with metal hardware","Moisture-wicking fabric technology","Shock-absorbing EVA midsole","Quick-dry material with UV protection"]

WRONG FORMATS (DO NOT USE):
❌ 2,5,8 (missing brackets)
❌ 135,174 (coordinate format - wrong!)
❌ [2,5] (wrong number of indices)
❌ ["Reason 1"] (wrong number of reasons)
❌ [2,5,8] ["Reason"] (not on separate lines)
❌ Any other text or explanations

# RULES  
CRITICAL FORMAT RULES:
1. Return EXACTLY {self.num_recs + 3} indices in [index,index,...] format
2. Return EXACTLY {self.num_recs + 3} reasons in ["reason","reason",...] format
3. Put indices and reasons on SEPARATE LINES
4. NO OTHER TEXT OR EXPLANATIONS ALLOWED

CONTENT RULES:
- Use only valid indices from available products
- Each reason must be 4-10 words, quoted
- reason example:"Emma Leggings - Clothing|Pants|Performance Fabrics","These leggings are a great complement to the Orestes Yoga Pant offering a similar style and function for active wear","Dual Handle Cardio Ball - Erin Recommends|Fitness Equipment"

DUPLICATE PREVENTION (CRITICAL):
- NEVER use the same index number twice
- Each product index must be unique
- Double-check your indices list for duplicates before submitting
- If you see any duplicate indices, replace them with different valid indices
- Example of WRONG: [2,5,8,2,15] (index 2 appears twice)
- Example of CORRECT: [2,5,8,12,15] (all indices unique)

OTHER RULES:
- Never mix gendered items
- Pet ≠ baby categories
- Vary reasoning using: {', '.join(selected_angles)}
- Avoid repetitive reasoning patterns
"""

        prompt_length = len(prompt)
        bt.logging.info(f"LLM QUERY Prompt length: {prompt_length}")
        
        if self.debug:
            token_count = PromptFactory.get_token_count(prompt)
            bt.logging.info(f"LLM QUERY Prompt Token count: {token_count}")
            bt.logging.debug(f"Persona: {self.persona}")
            bt.logging.debug(f"Season {season}")
            bt.logging.debug(f"Values: {', '.join(persona_data['priorities'])}")
            bt.logging.debug(f"Prompt: {prompt}")

        return prompt
    
    
    @staticmethod
    def get_token_count(prompt: str, encoding_name: str="o200k_base") -> int:
        encoding = PromptFactory._get_cached_encoding(encoding_name)
        tokens = encoding.encode(prompt)
        return len(tokens)
    
    
    @staticmethod
    @lru_cache(maxsize=4)
    def _get_cached_encoding(encoding_name: str):
        return tiktoken.get_encoding(encoding_name)
    
    
    @staticmethod
    def get_word_count(prompt: str) -> int:
        return len(prompt.split())

    @staticmethod
    def reconstruct_products_from_indices(indices_and_reasons: list, context: str) -> list:
        """
        Reconstruct full product data from indices and reasons using the original context.
        
        Args:
            indices_and_reasons: List containing [indices_list, reasons_list]
            context: Original context JSON string containing full product data
            
        Returns:
            List of dictionaries with full product data (sku, name, price, reason)
        """
        try:
            if not indices_and_reasons or len(indices_and_reasons) != 2:
                bt.logging.error("Invalid indices_and_reasons format")
                return []
                
            indices_list, reasons_list = indices_and_reasons
            
            # Parse original context
            context_products = json.loads(context)
            
            # Reconstruct products
            reconstructed_products = []
            for i, (index, reason) in enumerate(zip(indices_list, reasons_list)):
                if 0 <= index < len(context_products):
                    product = context_products[index].copy()
                    product['reason'] = reason
                    reconstructed_products.append(product)
                else:
                    bt.logging.error(f"Invalid index {index} for context with {len(context_products)} products")
                    
            return reconstructed_products
            
        except Exception as e:
            bt.logging.error(f"Error reconstructing products: {e}")
            return []    

    @staticmethod
    def tryparse_llm(input_str: str, num_recs: int = 5) -> list:
        """
        Take raw LLM output and parse to an array of [indices, reasons]
        Handles various formats including coordinates like "135,174"
        Returns exactly num_recs results after removing duplicates
        """
        try:
            if not input_str:
                bt.logging.error("Empty input string tryparse_llm")   
                return []
            
            # Clean up the input
            input_str = input_str.replace("```json", "").replace("```", "").strip()
            bt.logging.debug(f"Cleaned input: {input_str}")
            
            # Split input into lines
            lines = [line.strip() for line in input_str.split('\n') if line.strip()]
            
            indices_list = []
            reasons_list = []
            
            # Look for indices in various formats
            for line in lines:
                line = line.strip()
                
                # Format 1: [1,2,3] - standard bracket format
                if line.startswith('[') and line.endswith(']'):
                    content = line[1:-1].strip()
                    if all(c.isdigit() or c in ', ' for c in content):
                        try:
                            indices_list = [int(i.strip()) for i in content.split(',') if i.strip().isdigit()]
                            bt.logging.debug(f"Found indices (brackets): {indices_list}")
                            break
                        except ValueError:
                            continue
                
                # Format 2: "135,174" - coordinate format (no brackets)
                elif ',' in line and all(c.isdigit() or c in ', ' for c in line):
                    try:
                        indices_list = [int(i.strip()) for i in line.split(',') if i.strip().isdigit()]
                        bt.logging.debug(f"Found indices (coordinates): {indices_list}")
                        break
                    except ValueError:
                        continue
            
            # Look for reasons in various formats
            for line in lines:
                line = line.strip()
                
                # Format 1: ["reason1", "reason2"] - JSON array format
                if line.startswith('[') and line.endswith(']') and '"' in line:
                    try:
                        reasons_list = json.loads(line)
                        bt.logging.debug(f"Found reasons (JSON): {reasons_list}")
                        break
                    except json.JSONDecodeError:
                        # Fallback: manual parsing for quoted strings
                        import re
                        quoted_strings = re.findall(r'"([^"]*)"', line)
                        if quoted_strings:
                            reasons_list = quoted_strings
                            bt.logging.debug(f"Found reasons (regex): {reasons_list}")
                            break
                
                # Format 2: Single quoted strings without brackets
                elif line.startswith('"') and line.endswith('"'):
                    reasons_list = [line[1:-1]]  # Remove quotes
                    bt.logging.debug(f"Found single reason: {reasons_list}")
                    break
            
            # Validate and return results
            if indices_list and reasons_list:
                # Remove any duplicate indices while preserving order
                seen = set()
                unique_indices = []
                unique_reasons = []
                for idx, reason in zip(indices_list, reasons_list):
                    if idx not in seen:
                        seen.add(idx)
                        unique_indices.append(idx)
                        unique_reasons.append(reason)
                    else:
                        bt.logging.warning(f"Duplicate index found and removed: {idx}")
                
                # Limit to exactly num_recs results
                indices_list = unique_indices[:num_recs]
                reasons_list = unique_reasons[:num_recs]
                
                if(len(indices_list) != num_recs or len(reasons_list) != num_recs):
                    bt.logging.error(f"Parsed number is not coincidense with num_recs: {num_recs}")
                else:
                    bt.logging.info(f"Successfully parsed: {len(indices_list)} indices and {len(reasons_list)} reasons (limited to {num_recs})")

                return [indices_list, reasons_list]
            else:
                bt.logging.error(f"Could not find valid indices or reasons in LLM output")
                bt.logging.error(f"Input: {input_str}")
                bt.logging.error(f"Lines: {lines}")
                bt.logging.error(f"Indices found: {indices_list}")
                bt.logging.error(f"Reasons found: {reasons_list}")
            
            return []
                
        except Exception as e:
            bt.logging.error(f"Error parsing LLM output: {e}")
            bt.logging.error(f"Input was: {input_str}")
            return []