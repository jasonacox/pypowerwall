# Tesla Powerwall Vitals Data

This script, [pull_vitals.py](pull_vitals.py) pulls the Powerwall Vitals API and returns a JSON result.

## Notes

* Work in Progress
* API Endpoint on Powerwall: /api/devices/vitals
* Result is a protobuf binary payload

## Requirements

This API send a protobuf payload.  It requires the necessary protobuf definition and libraries: 

Before using this be sure to install the protobuf module:
```bash
# Install protobuf
pip install protobuf
```

The script uses the generated file, [tesla_pb2.py](tesla_pb2.py).  This is generated from the `protoc` compiler. If you wish to compile the tesla.proto definition file yourself, install protobuf of your systems (e.g. `brew install protobuf`) and run:

```bash
# Run protobuf compiler to build definition python code
protoc --python_out=. tesla.proto 
```

## Credits

* Protobuf definition [tesla.proto](tesla.proto) thanks to @brianhealey.  See https://github.com/vloschiavo/powerwall2/issues/51#issuecomment-923574346 