// =========================================================================
// 1. 본초(Herb) 노드 생성 - 갈근 (칡)
// 문서의 1. 이름 및 12. 고문헌(독성 여부) 참고
// =========================================================================
MERGE (h:Herb {herb_id: 'H_002'}) // 강활에 이어 H_002로 임의 부여
ON CREATE SET h.name = '갈근', 
              // 수많은 이명 중 대표적인 것들을 배열로 저장
              h.synonyms = ['칡', '건갈', '과근', '시갈근', '분갈', '녹곽', '감갈'], 
              h.toxicity = '무독' // 동의보감: "無毒"

// =========================================================================
// 2. 기미론(Nature) 속성 연결
// 문서의 3) 성미: 甘辛平 (달고 맵고 평하다)
// =========================================================================
MERGE (nt:NatureTemp {name: '평'})  // 평(平)
MERGE (ta1:NatureTaste {name: '감'}) // 단맛(甘)
MERGE (ta2:NatureTaste {name: '신'}) // 매운맛(辛)

MERGE (h)-[:HAS_TEMP]->(nt)
MERGE (h)-[:HAS_TASTE]->(ta1)
MERGE (h)-[:HAS_TASTE]->(ta2)

// =========================================================================
// 3. 귀경(Meridian) 속성 연결
// 문서의 4) 귀경: 脾胃 (비, 위)
// =========================================================================
MERGE (m1:Meridian {name: '비'})
MERGE (m2:Meridian {name: '위'})

MERGE (h)-[:ACTS_ON]->(m1)
MERGE (h)-[:ACTS_ON]->(m2)

// =========================================================================
// 4. 효능(Efficacy) 속성 연결
// 문서의 6) 효능분류 및 7) 효능
// =========================================================================
MERGE (e1:Efficacy {name: '발산풍열'})
MERGE (e2:Efficacy {name: '생진'})
MERGE (e3:Efficacy {name: '승양지사'})
MERGE (e4:Efficacy {name: '투진'})
MERGE (e5:Efficacy {name: '해기퇴열'})

MERGE (h)-[:HAS_EFFICACY]->(e1)
MERGE (h)-[:HAS_EFFICACY]->(e2)
MERGE (h)-[:HAS_EFFICACY]->(e3)
MERGE (h)-[:HAS_EFFICACY]->(e4)
MERGE (h)-[:HAS_EFFICACY]->(e5)

// =========================================================================
// 5. 증상(Symptom) 속성 연결
// 문서의 8) 주치
// =========================================================================
MERGE (s1:Symptom {name: '소갈'}) // 갈증
MERGE (s2:Symptom {name: '구갈'})
MERGE (s3:Symptom {name: '항배강통'}) // 목과 등이 뻣뻣하고 아픈 증상
MERGE (s4:Symptom {name: '고혈압경항강통'})
MERGE (s5:Symptom {name: '마진불투'}) // 홍역이 잘 돋지 않음
MERGE (s6:Symptom {name: '설사'})
MERGE (s7:Symptom {name: '외감발열두통'})

MERGE (h)-[:TREATS]->(s1)
MERGE (h)-[:TREATS]->(s2)
MERGE (h)-[:TREATS]->(s3)
MERGE (h)-[:TREATS]->(s4)
MERGE (h)-[:TREATS]->(s5)
MERGE (h)-[:TREATS]->(s6)
MERGE (h)-[:TREATS]->(s7)

// =========================================================================
// 6. 처방(Formula) 연결
// 문서의 8) 주치 및 관련처방 표에 명시된 방제
// =========================================================================

// [처방 1] 승마갈근탕 (구갈 치료)
MERGE (f1:Formula {formula_id: 'F_001', name: '승마갈근탕'})
MERGE (f1)-[:CONTAINS]->(h)
// 나머지 구성 약재도 그래프에 노드로 만들어 연결
MERGE (herb_sm:Herb {name: '승마'})
MERGE (herb_jy:Herb {name: '작약'})
MERGE (herb_gc:Herb {name: '감초'})
MERGE (f1)-[:CONTAINS]->(herb_sm)
MERGE (f1)-[:CONTAINS]->(herb_jy)
MERGE (f1)-[:CONTAINS]->(herb_gc)

// [처방 2] 가미전씨백출산 (소갈 치료)
MERGE (f2:Formula {formula_id: 'F_002', name: '가미전씨백출산'})
MERGE (f2)-[:CONTAINS]->(h)

// [처방 3] 칠미백출산 (구갈 치료)
MERGE (f3:Formula {formula_id: 'F_003', name: '칠미백출산'})
MERGE (f3)-[:CONTAINS]->(h)

// [처방 4] 오즙옥천환 (소갈 치료)
MERGE (f4:Formula {formula_id: 'F_004', name: '오즙옥천환'})
MERGE (f4)-[:CONTAINS]->(h)