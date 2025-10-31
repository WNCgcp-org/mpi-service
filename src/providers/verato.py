"""
Minimal Verato MPI Module for Wellnecity Silkroad Integration
Designed to be pluggable and collect Verato IDs for ML training
"""

import os
import json
import asyncio
import hashlib
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import aiohttp
import redis
from pymongo import MongoClient
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VeratoConfig:
    """Verato API Configuration"""
    api_key: str = os.getenv('VERATO_API_KEY', '')
    endpoint: str = os.getenv('VERATO_ENDPOINT', 'https://api.verato.com')
    timeout: int = int(os.getenv('VERATO_TIMEOUT', '5000'))
    max_retries: int = int(os.getenv('VERATO_MAX_RETRIES', '3'))
    cache_ttl: int = int(os.getenv('VERATO_CACHE_TTL', '86400'))  # 24 hours

    # MongoDB settings
    mongo_uri: str = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    mongo_db: str = os.getenv('MPI_DB', 'mpi_service')
    mongo_collection: str = os.getenv('MPI_COLLECTION', 'verato_ids')

    # Redis settings
    redis_host: str = os.getenv('REDIS_HOST', 'localhost')
    redis_port: int = int(os.getenv('REDIS_PORT', '6379'))
    redis_db: int = int(os.getenv('REDIS_DB', '0'))


class VeratoModule:
    """
    Verato MPI Provider Module
    Handles patient matching via Verato API with caching and persistence
    """

    def __init__(self, config: VeratoConfig = None):
        self.config = config or VeratoConfig()
        self._init_connections()

    def _init_connections(self):
        """Initialize database connections"""
        try:
            # MongoDB connection
            self.mongo_client = MongoClient(self.config.mongo_uri)
            self.db = self.mongo_client[self.config.mongo_db]
            self.collection = self.db[self.config.mongo_collection]

            # Create indexes
            self.collection.create_index('verato_id')
            self.collection.create_index('ssn_hash')
            self.collection.create_index('created_at')

            # Redis connection
            self.redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                decode_responses=True
            )

            logger.info("Database connections initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            raise

    def _hash_ssn(self, ssn: str) -> str:
        """Create a hash of SSN for cache key"""
        if not ssn:
            return None
        # Remove any formatting
        clean_ssn = ''.join(filter(str.isdigit, ssn))
        return hashlib.sha256(clean_ssn.encode()).hexdigest()[:16]

    def _build_cache_key(self, patient_data: Dict) -> Optional[str]:
        """Build a cache key from patient data"""
        ssn = patient_data.get('ssn', '').replace('-', '')
        if ssn:
            return f"verato:ssn:{self._hash_ssn(ssn)}"

        # Fallback to name + DOB if no SSN
        first = patient_data.get('first_name', '').lower()
        last = patient_data.get('last_name', '').lower()
        dob = patient_data.get('dob', '')

        if first and last and dob:
            key_string = f"{first}:{last}:{dob}"
            key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]
            return f"verato:demo:{key_hash}"

        return None

    async def get_mpi_id(self, patient_data: Dict) -> Dict[str, Any]:
        """
        Main entry point - get Verato ID for patient

        Args:
            patient_data: Dictionary with patient demographics

        Returns:
            Dict with verato_id, confidence, and metadata
        """
        try:
            # 1. Check cache first
            cache_key = self._build_cache_key(patient_data)
            if cache_key:
                cached = self.redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache hit for {cache_key}")
                    return json.loads(cached)

            # 2. Check MongoDB
            ssn_hash = self._hash_ssn(patient_data.get('ssn', ''))
            if ssn_hash:
                existing = self.collection.find_one({'ssn_hash': ssn_hash})
                if existing:
                    logger.info(f"MongoDB hit for SSN hash {ssn_hash}")
                    result = {
                        'verato_id': existing['verato_id'],
                        'confidence': existing.get('confidence', 0.95),
                        'source': 'database'
                    }
                    # Update cache
                    if cache_key:
                        self.redis_client.setex(
                            cache_key,
                            self.config.cache_ttl,
                            json.dumps(result)
                        )
                    return result

            # 3. Call Verato API
            result = await self._call_verato_api(patient_data)

            # 4. Store in MongoDB
            self._store_result(patient_data, result)

            # 5. Update cache
            if cache_key:
                self.redis_client.setex(
                    cache_key,
                    self.config.cache_ttl,
                    json.dumps(result)
                )

            return result

        except Exception as e:
            logger.error(f"Error getting Verato ID: {e}")
            return {
                'verato_id': None,
                'error': str(e),
                'source': 'error'
            }

    async def _call_verato_api(self, patient_data: Dict) -> Dict:
        """
        Call Verato API to get patient ID
        Based on SnapLogic pipeline configuration
        """
        # Generate tracking ID for this request
        import uuid
        tracking_id = str(uuid.uuid4())

        # Build Verato request payload matching SnapLogic format
        verato_payload = {
            'content': {
                'identity': {
                    'sources': [{
                        'name': f"wellnecity.{patient_data.get('data_version', 'v1')}",
                        'id': patient_data.get('patient_id', '')
                    }],
                    'emails': [],
                    'addresses': [],
                    'phoneNumbers': [],
                    'names': [],
                    'datesOfBirth': [],
                    'ssns': [],
                    'genders': []
                },
                'responseIdentityFormatNames': ['DEFAULT'],
                'trackingId': tracking_id
            }
        }

        content = verato_payload['content']['identity']

        # Add emails (filter out empty/nan values like SnapLogic)
        emails = []
        for email_field in ['work_email', 'home_email', 'other_email']:
            email = patient_data.get(email_field)
            if email and email not in ['nan', 'not-provided', '']:
                emails.append(email)
        if emails:
            content['emails'] = emails

        # Add address
        if patient_data.get('address_1') or patient_data.get('city'):
            content['addresses'] = [{
                'line1': patient_data.get('address_1', ''),
                'line2': patient_data.get('address_2', ''),
                'city': patient_data.get('city', ''),
                'state': patient_data.get('state', ''),
                'postalCode': patient_data.get('zip', '')
            }]

        # Add name (filter out 'not-provided' and 'nan')
        name_obj = {}
        if patient_data.get('first_name') and patient_data['first_name'] not in ['nan', 'not-provided']:
            name_obj['first'] = patient_data['first_name']
        if patient_data.get('middle_name') and patient_data['middle_name'] not in ['nan', 'not-provided']:
            name_obj['middle'] = patient_data['middle_name']
        if patient_data.get('last_name') and patient_data['last_name'] not in ['nan', 'not-provided']:
            name_obj['last'] = patient_data['last_name']
        if patient_data.get('suffix') and patient_data['suffix'] not in ['nan', 'not-provided']:
            name_obj['suffix'] = patient_data['suffix']

        if name_obj:
            content['names'] = [name_obj]

        # Add date of birth (formatted as yyyyMMdd)
        if patient_data.get('dob') and patient_data['dob'] not in ['nan', '']:
            # Convert to yyyyMMdd format
            dob = patient_data['dob'].replace('-', '').replace('/', '')
            content['datesOfBirth'] = [dob]

        # Add SSN (filter out nan)
        if patient_data.get('ssn') and patient_data['ssn'] not in ['nan', '']:
            content['ssns'] = [patient_data['ssn'].replace('-', '')]

        # Add gender
        if patient_data.get('gender') and patient_data['gender'] not in ['nan', '']:
            content['genders'] = [patient_data['gender']]

        # Add phone numbers (complex formatting like SnapLogic)
        phone_numbers = []
        for phone_field in ['home_phone', 'work_phone', 'other_phone']:
            phone = patient_data.get(phone_field)
            if phone and phone not in ['nan', 'not-provided', 'not-included', '']:
                # Clean phone number
                clean_phone = ''.join(filter(str.isdigit, str(phone)))
                if len(clean_phone) == 10:
                    phone_numbers.append({
                        'countryCode': '1',
                        'areaCode': clean_phone[:3],
                        'number': clean_phone[3:],
                        'extension': ''
                    })
                elif len(clean_phone) == 11 and clean_phone[0] == '1':
                    phone_numbers.append({
                        'countryCode': '1',
                        'areaCode': clean_phone[1:4],
                        'number': clean_phone[4:],
                        'extension': ''
                    })

        if phone_numbers:
            content['phoneNumbers'] = phone_numbers

        # Make API call
        headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }

        # Add authentication if using API key
        if self.config.api_key:
            headers['X-API-Key'] = self.config.api_key

        # Use the actual Verato endpoint from SnapLogic
        endpoint = self.config.endpoint or 'https://cust0161-dev.verato-connect.com/link-ws/svc/postIdentity'

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    endpoint,
                    json=verato_payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout/1000)
                ) as response:

                    if response.status == 200:
                        data = await response.json()

                        # Extract Verato linkId from response
                        # Based on SnapLogic: $response.entity.content.linkId
                        link_id = None
                        if 'entity' in data:
                            link_id = data.get('entity', {}).get('content', {}).get('linkId')
                        elif 'content' in data:
                            link_id = data.get('content', {}).get('linkId')
                        elif 'linkId' in data:
                            link_id = data.get('linkId')

                        return {
                            'verato_id': link_id,
                            'confidence': data.get('confidence', 0.95),
                            'tracking_id': tracking_id,
                            'source': 'api'
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Verato API error: {response.status} - {error_text}")
                        return {
                            'verato_id': None,
                            'error': f"API returned {response.status}",
                            'source': 'api_error'
                        }

            except asyncio.TimeoutError:
                logger.error("Verato API timeout")
                return {
                    'verato_id': None,
                    'error': 'timeout',
                    'source': 'timeout'
                }
            except Exception as e:
                logger.error(f"Verato API exception: {e}")
                return {
                    'verato_id': None,
                    'error': str(e),
                    'source': 'exception'
                }

    def _store_result(self, patient_data: Dict, result: Dict):
        """Store Verato result in MongoDB"""
        try:
            if not result.get('verato_id'):
                return

            document = {
                'verato_id': result['verato_id'],
                'confidence': result.get('confidence', 0),
                'ssn_hash': self._hash_ssn(patient_data.get('ssn', '')),
                'created_at': datetime.utcnow(),
                'source_data': {
                    # Store limited data for debugging
                    'has_ssn': bool(patient_data.get('ssn')),
                    'has_name': bool(patient_data.get('first_name') and patient_data.get('last_name')),
                    'has_dob': bool(patient_data.get('dob')),
                    'has_address': bool(patient_data.get('address'))
                }
            }

            # Upsert to handle duplicates
            self.collection.update_one(
                {'verato_id': result['verato_id']},
                {'$set': document},
                upsert=True
            )

            logger.info(f"Stored Verato ID {result['verato_id']} in MongoDB")

        except Exception as e:
            logger.error(f"Failed to store in MongoDB: {e}")

    async def batch_process(self, patient_records: list, max_concurrent: int = 40):
        """
        Process multiple patient records concurrently
        Matches SnapLogic's 40 concurrent calls capability
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(patient_data):
            async with semaphore:
                return await self.get_mpi_id(patient_data)

        tasks = [process_with_limit(patient) for patient in patient_records]
        results = await asyncio.gather(*tasks)

        return results

    def get_stats(self) -> Dict:
        """Get module statistics"""
        try:
            total_records = self.collection.count_documents({})
            cache_keys = self.redis_client.dbsize()

            # Get recent success rate
            recent = list(self.collection.find(
                {'created_at': {'$gte': datetime.utcnow() - timedelta(hours=1)}},
                {'confidence': 1}
            ).limit(1000))

            avg_confidence = sum(r.get('confidence', 0) for r in recent) / len(recent) if recent else 0

            return {
                'total_verato_ids': total_records,
                'cache_entries': cache_keys,
                'recent_avg_confidence': avg_confidence,
                'recent_count': len(recent)
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Standalone test function
async def test_verato_module():
    """Test the Verato module with sample data"""
    module = VeratoModule()

    test_patient = {
        'ssn': '123-45-6789',
        'first_name': 'John',
        'last_name': 'Smith',
        'dob': '1980-01-01',
        'gender': 'M',
        'address': '123 Main St',
        'city': 'Boston',
        'state': 'MA',
        'zip': '02101'
    }

    result = await module.get_mpi_id(test_patient)
    print(f"Test result: {json.dumps(result, indent=2)}")

    stats = module.get_stats()
    print(f"Module stats: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_verato_module())