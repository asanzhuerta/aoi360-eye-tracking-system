using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace AOI360.Runtime.Experiment
{
    internal static class ExperimentRuntimeUi
    {
        private static TMP_FontAsset cachedFontAsset;
        private static Sprite cachedWhiteSprite;

        public static TMP_FontAsset ResolveFontAsset()
        {
            if (cachedFontAsset != null)
            {
                return cachedFontAsset;
            }

            cachedFontAsset = TMP_Settings.defaultFontAsset;
            if (cachedFontAsset == null)
            {
                cachedFontAsset = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            }

            return cachedFontAsset;
        }

        public static Sprite GetWhiteSprite()
        {
            if (cachedWhiteSprite != null)
            {
                return cachedWhiteSprite;
            }

            cachedWhiteSprite = Sprite.Create(
                Texture2D.whiteTexture,
                new Rect(0f, 0f, 1f, 1f),
                new Vector2(0.5f, 0.5f)
            );

            return cachedWhiteSprite;
        }

        public static RectTransform CreateUiObject(string name, Transform parent, Vector2 anchorMin, Vector2 anchorMax)
        {
            GameObject gameObject = new GameObject(name, typeof(RectTransform));
            RectTransform rectTransform = gameObject.GetComponent<RectTransform>();
            rectTransform.SetParent(parent, false);
            rectTransform.anchorMin = anchorMin;
            rectTransform.anchorMax = anchorMax;
            rectTransform.offsetMin = Vector2.zero;
            rectTransform.offsetMax = Vector2.zero;
            rectTransform.localScale = Vector3.one;
            return rectTransform;
        }

        public static Image AddPanelImage(RectTransform target, Color color)
        {
            Image image = target.gameObject.AddComponent<Image>();
            image.sprite = GetWhiteSprite();
            image.type = Image.Type.Sliced;
            image.color = color;
            return image;
        }

        public static TextMeshProUGUI CreateText(
            string name,
            Transform parent,
            string text,
            float fontSize,
            FontStyles fontStyle,
            TextAlignmentOptions alignment,
            Color color
        )
        {
            RectTransform rectTransform = CreateUiObject(name, parent, new Vector2(0f, 0f), new Vector2(1f, 1f));
            TextMeshProUGUI textComponent = rectTransform.gameObject.AddComponent<TextMeshProUGUI>();
            textComponent.font = ResolveFontAsset();
            textComponent.text = text;
            textComponent.fontSize = fontSize;
            textComponent.fontStyle = fontStyle;
            textComponent.alignment = alignment;
            textComponent.color = color;
            textComponent.enableWordWrapping = true;
            textComponent.margin = new Vector4(20f, 12f, 20f, 12f);
            return textComponent;
        }

        public static Button CreateButton(string name, Transform parent, Color backgroundColor)
        {
            RectTransform rectTransform = CreateUiObject(name, parent, new Vector2(0f, 0f), new Vector2(1f, 1f));
            Image image = rectTransform.gameObject.AddComponent<Image>();
            image.sprite = GetWhiteSprite();
            image.color = backgroundColor;

            Button button = rectTransform.gameObject.AddComponent<Button>();
            ColorBlock colors = button.colors;
            colors.normalColor = backgroundColor;
            colors.highlightedColor = backgroundColor * 1.15f;
            colors.pressedColor = backgroundColor * 0.9f;
            colors.selectedColor = backgroundColor * 1.1f;
            colors.disabledColor = new Color(backgroundColor.r, backgroundColor.g, backgroundColor.b, 0.4f);
            button.colors = colors;
            button.targetGraphic = image;
            return button;
        }
    }
}
