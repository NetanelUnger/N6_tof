"""Decode CRC-validated N6 display frames; no GUI or transport side effects."""
import io
import math
import numpy as np
from PIL import Image

MODES = {1: 'RAW', 2: 'UINT16', 3: 'UINT8', 4: 'JPEG'}
CHANNELS = {1:'Depth', 2:'Amplitude', 3:'Ambient', 4:'Reflectance', 5:'Confidence'}


def decode_pixels(frame):
    width, height = frame['width'], frame['height']
    if not 0 < width <= 54 or not 0 < height <= 42:
        raise ValueError('Invalid dimensions')
    count = width*height
    payload, code = frame['payload'], frame['pixel_format']
    if code == 1:
        if len(payload) != count*4: raise ValueError('RAW size mismatch')
        pixels = np.frombuffer(payload, dtype='<f4').copy()
    elif code in (2,3):
        if len(payload) != count*(2 if code==2 else 1): raise ValueError('Quantized size mismatch')
        values = np.frombuffer(payload, dtype='<u2' if code==2 else 'u1')
        pixels = frame['base']+(values.astype(np.float32)-1)*frame['step']
        pixels[values==0] = np.nan
    elif code == 4:
        mask_size = (count+7)//8
        jpeg, mask = payload[:-mask_size], payload[-mask_size:]
        if len(jpeg)<4 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            raise ValueError('Invalid JPEG boundaries')
        if count%8 and mask[-1] >> (count%8): raise ValueError('Nonzero JPEG mask padding')
        with Image.open(io.BytesIO(jpeg)) as image:
            if image.format!='JPEG' or image.size!=(width,height): raise ValueError('JPEG dimensions mismatch')
            values=np.asarray(image.convert('L'), dtype=np.float32).reshape(-1)
        valid=np.unpackbits(np.frombuffer(mask,dtype='u1'),bitorder='little')[:count].astype(bool)
        pixels=frame['base']+(np.maximum(1,values)-1)*frame['step']
        pixels[~valid]=np.nan
    else:
        raise ValueError('Not a display image encoding: '+str(code))
    return pixels.reshape(height,width)


def colorize(pixels):
    """Per-frame range, invalid pixels dark. Returns RGB plus actual range."""
    valid=np.isfinite(pixels)
    if valid.any():
        low,high=float(pixels[valid].min()),float(pixels[valid].max())
        normalized=np.zeros(pixels.shape,dtype=np.float32)
        normalized[valid]=(pixels[valid]-low)/(high-low) if high>low else .5
    else:
        low=high=None
        normalized=np.zeros(pixels.shape,dtype=np.float32)
    # Smooth blue/cyan/yellow/red ramp; the UI labels the dynamic scale.
    rgb=np.stack([np.clip(1.5-abs(4*normalized-3),0,1),
                  np.clip(1.5-abs(4*normalized-2),0,1),
                  np.clip(1.5-abs(4*normalized-1),0,1)],axis=-1)
    rgb=(rgb*255).astype('uint8');rgb[~valid]=(18,23,30)
    return Image.fromarray(rgb),low,high
