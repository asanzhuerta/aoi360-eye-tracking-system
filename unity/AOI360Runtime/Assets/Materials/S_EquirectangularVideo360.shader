Shader "AOI360/Equirectangular Video"
{
    Properties
    {
        _MainTex("Video Texture", 2D) = "black" {}
        _Tint("Tint", Color) = (1,1,1,1)
        _YawOffsetDegrees("Yaw Offset Degrees", Float) = 0
        _VerticalOffsetDegrees("Vertical Offset Degrees", Float) = 0
        _FlipHorizontal("Flip Horizontal", Float) = 0
        _FlipVertical("Flip Vertical", Float) = 0
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
            "RenderPipeline" = "UniversalPipeline"
        }

        Pass
        {
            Name "ForwardUnlit"
            Tags { "LightMode" = "UniversalForward" }

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

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _Tint;
                float _YawOffsetDegrees;
                float _VerticalOffsetDegrees;
                float _FlipHorizontal;
                float _FlipVertical;
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

                half4 color = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, float2(u, v));
                color.rgb *= _Tint.rgb;
                color.a = 1.0;
                return color;
            }
            ENDHLSL
        }
    }
}
