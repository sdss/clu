import asyncio
from clu.legacy import TronConnection

def report_fwhm(fwhm_key):
    # Get the value for the trimmed mean
    tmean = fwhm_key.value[1]
    print(f'The FWHM is {tmean} arcsec.')

async def main():
    tron = TronConnection(host='localhost', port=6093, models=['guider'])
    tron.models['guider']['fwhm'].register_callback(report_fwhm)
    await tron.start()
    await tron.run_forever()

asyncio.run(main())
