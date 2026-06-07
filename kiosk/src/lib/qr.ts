import QRCode from 'qrcode';

export async function generateQRSVG(text: string, size = 512): Promise<string> {
  return await QRCode.toString(text, {
    type: 'svg',
    margin: 1,
    width: size,
    errorCorrectionLevel: 'M',
    color: { dark: '#0f172a', light: '#ffffff' },
  });
}
