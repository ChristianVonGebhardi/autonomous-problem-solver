package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.Referral;
import com.healthcare.referral.domain.enums.ReferralStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface ReferralRepository extends JpaRepository<Referral, Long> {

    Optional<Referral> findByReferralNumber(String referralNumber);

    List<Referral> findByStatus(ReferralStatus status);

    List<Referral> findByPatientId(Long patientId);

    List<Referral> findByAssignedProviderId(Long providerId);

    @Query("SELECT r FROM Referral r WHERE r.status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED') ORDER BY r.createdAt DESC")
    List<Referral> findActiveReferrals();

    @Query("""
            SELECT r FROM Referral r
            WHERE r.status = :status
              AND r.updatedAt < :cutoffTime
            """)
    List<Referral> findStaleReferralsByStatus(
            @Param("status") ReferralStatus status,
            @Param("cutoffTime") LocalDateTime cutoffTime);

    @Query("""
            SELECT r.status as status, COUNT(r) as count
            FROM Referral r
            GROUP BY r.status
            """)
    List<Object[]> countByStatus();

    @Query("""
            SELECT r FROM Referral r
            WHERE r.priorAuthRequired = true
              AND r.priorAuthStatus IS NULL
              AND r.status = 'MATCHED'
            """)
    List<Referral> findReferralsPendingPriorAuth();

    @Query("""
            SELECT r FROM Referral r
            WHERE r.status = 'SENT_TO_SPECIALIST'
              AND r.specialistSentAt < :cutoffTime
            """)
    List<Referral> findReferralsAwaitingSpecialistResponse(
            @Param("cutoffTime") LocalDateTime cutoffTime);

    @Query(value = """
            SELECT
                DATE(created_at) as ref_date,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status IN ('CANCELLED', 'FAILED') THEN 1 ELSE 0 END) as failed
            FROM referrals
            WHERE created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY ref_date
            """, nativeQuery = true)
    List<Object[]> getDailyReferralStats(@Param("since") LocalDateTime since);

    long countByStatus(ReferralStatus status);
}