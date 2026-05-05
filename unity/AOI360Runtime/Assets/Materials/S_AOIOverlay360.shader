Shader "AOI360/Equirectangular Overlay"
{
    Properties
    {
        _BaseMap("Overlay Texture", 2D) = "black" {}
        _BaseColor("Tint", Color) = (1,1,1,1)
        _FocusedAoiColor("Focused AOI Color", Color) = (0,0,0,0)
        _YawOffsetDegrees("Yaw Offset Degrees", Float) = 0
        _VerticalOffsetDegrees("Vertical Offset Degrees", Float) = 0
        _FlipHorizontal("Flip Horizontal", Float) = 0
        _FlipVertical("Flip Vertical", Float) = 0
        _BaseOpacity("Base Opacity", Float) = 0.12
        _FocusedOpacity("Focused Opacity", Float) = 0.4
        _HasFocusedAoi("Has Focused AOI", Float) = 0
        _FocusedColorTolerance("Focused Color Tolerance", Float) = 0.0025
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Transparent"
            "Queue" = "Transparent"
            "RenderPipeline" = "UniversalPipeline"
        }

        Pass
        {
            Name "ForwardUnlit"
            Tags { "LightMode" = "UniversalForward" }

            Blend SrcAlpha OneMinusSrcAlpha
            Cull Off
            ZWrite Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionOS : TEXCOORD0;
            };

            TEXTURE2D(_BaseMap);
            SAMPLER(sampler_BaseMap);

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseColor;
                float4 _FocusedAoiColor;
                float _YawOffsetDegrees;
                float _VerticalOffsetDegrees;
                float _FlipHorizontal;
                float _FlipVertical;
                float _BaseOpacity;
                float _FocusedOpacity;
                float _HasFocusedAoi;
                float _FocusedColorTolerance;
            CBUFFER_END

            Varyings Vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.positionOS = input.positionOS.xyz;
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float3 dir = normalize(input.positionOS);
                float azimuth = atan2(dir.x, dir.z);
                float elevation = asin(clamp(dir.y, -1.0, 1.0));

                float u = frac(((azimuth + PI) / (2.0 * PI)) + (_YawOffsetDegrees / 360.0));
                float adjustedElevation = elevation + radians(_VerticalOffsetDegrees);
                float v = 0.5 - (adjustedElevation / PI);

                if (_FlipHorizontal > 0.5)
                {
                    u = 1.0 - u;
                }

                if (_FlipVertical > 0.5)
                {
                    v = 1.0 - v;
                }

                half4 color = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, float2(u, v));
                if (all(color.rgb <= half3(0.001, 0.001, 0.001)))
                {
                    return half4(0, 0, 0, 0);
                }

                float maxChannelDelta = max(max(abs(color.r - _FocusedAoiColor.r), abs(color.g - _FocusedAoiColor.g)), abs(color.b - _FocusedAoiColor.b));
                float isFocused = (_HasFocusedAoi > 0.5 && maxChannelDelta <= _FocusedColorTolerance) ? 1.0 : 0.0;
                float alpha = lerp(_BaseOpacity, _FocusedOpacity, isFocused);

                color.rgb *= _BaseColor.rgb;
                color.a = alpha * _BaseColor.a;
                return color;
            }
            ENDHLSL
        }
    }
}
