import boto3
import json
import time
import sys
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests

def create_index(collection_endpoint, region):
    credentials = boto3.Session().get_credentials()
    service = 'aoss'
    
    url = f"{collection_endpoint}/aiops-incidents-index"
    host = collection_endpoint.replace("https://", "")
    
    payload = {
        "settings": {
            "index": {
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss"
                    }
                },
                "text": {
                    "type": "text"
                },
                "metadata": {
                    "type": "text"
                }
            }
        }
    }
    
    body = json.dumps(payload)
    
    # Retry loop for eventual consistency
    for i in range(30):
        try:
            request = AWSRequest(method='PUT', url=url, data=body)
            SigV4Auth(credentials, service, region).add_auth(request)
            
            headers = dict(request.headers)
            headers['Content-Type'] = 'application/json'
            
            r = requests.put(url, headers=headers, data=body)
            
            if r.status_code == 200:
                print("Index created successfully")
                return
            elif "resource_already_exists_exception" in r.text:
                 print("Index already exists")
                 return
            elif r.status_code == 403:
                print(f"Waiting for IAM propagation (attempt {i+1}/30)...")
            else:
                print(f"Failed to create index (attempt {i+1}): {r.status_code} {r.text}")
                
        except Exception as e:
            print(f"Error (attempt {i+1}): {e}")
            
        time.sleep(20)
        
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_index.py <endpoint> <region>")
        sys.exit(1)
        
    create_index(sys.argv[1], sys.argv[2])
