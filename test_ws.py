import asyncio
import websockets
import json

async def test():
    try:
        ws = await websockets.connect('ws://localhost:8765/ws')
        print('✓ Connected to ws://localhost:8765/ws')
        
        handshake = {
            'type': 'handshake',
            'data': {
                'orchestrator_id': 'test-001',
                'metadata': {'name': 'Test', 'location': 'localhost'}
            }
        }
        await ws.send(json.dumps(handshake))
        print('✓ Sent handshake')
        
        resp = await ws.recv()
        print(f'✓ Response: {resp}')
        
        await ws.close()
        print('✓ Test successful!')
    except Exception as e:
        print(f'✗ Error: {e}')

asyncio.run(test())


